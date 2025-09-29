# Streamlit App: Upload Excel, Map Column, Process via Assistant Prompt

import streamlit as st
import pandas as pd
from openai import OpenAI
import os
import time

# --- Initialize session state variables ---
if "processed_df" not in st.session_state:
    st.session_state.processed_df = None
if "has_processed" not in st.session_state:
    st.session_state.has_processed = False
if "original_df" not in st.session_state:
    st.session_state.original_df = None
if "selected_col" not in st.session_state:
    st.session_state.selected_col = None

# Function to handle table edits - improved to ensure DataFrame type
def handle_table_edit():
    # Ensure we're working with a DataFrame
    if isinstance(st.session_state.editable_table, pd.DataFrame):
        st.session_state.processed_df = st.session_state.editable_table.copy()
    else:
        # If somehow not a DataFrame, convert it properly
        try:
            st.session_state.processed_df = pd.DataFrame(st.session_state.editable_table)
        except Exception as e:
            st.error(f"Error updating table: {str(e)}")

# --- Setup ---
# Set your API key
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY  # Replace with your actual key
client = OpenAI()

# --- App UI ---
st.title("🔍 RFQ Assistant")
st.markdown("""
Upload an Excel file, select a column to analyze (e.g. Product Description), and review generated Description breakdowns.
""")

# --- Step 1: Upload Excel ---
uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

if uploaded_file:
    # Only read the file if we haven't already processed it
    if not st.session_state.has_processed:
        df = pd.read_excel(uploaded_file)
        st.session_state.original_df = df.copy()
        st.success(f"Uploaded file with {df.shape[0]} rows and {df.shape[1]} columns.")
    else:
        df = st.session_state.original_df.copy()
        st.success(f"Using previously uploaded file with {df.shape[0]} rows and {df.shape[1]} columns.")

    # --- Step 2: Select the column to map ---
    if not st.session_state.has_processed:
        st.session_state.selected_col = st.selectbox("Select column for Product Description:", df.columns)
    else:
        # Display the selected column but disable interaction
        st.selectbox("Select column for Product Description:", 
                    [st.session_state.selected_col], 
                    index=0, 
                    disabled=True)
    
    selected_col = st.session_state.selected_col

    # --- Step 3: Process Button ---
    process_clicked = st.button("Process with Assistant", disabled=st.session_state.has_processed)
    
    # Execute processing only if button is clicked and we haven't processed yet
    if process_clicked and not st.session_state.has_processed:
        progress = st.progress(0, "Running assistant on each row...")
        output_texts = []

        for i, row in df.iterrows():
            desc = str(row[selected_col])

            try:
                response = client.responses.create(
                    model="o4-mini",  # or your choice
                    prompt={
                        "id": "pmpt_68c149f517d08194a4e834fa5fc92e4901308fd21d68d48f",
                        "version": "2",
                        "variables": {
                            "product_description": desc
                        }
                    },
                    reasoning={"effort": "medium"},
                    text={"format": {"type": "text"}}
                )
                # ✅ Show debug output inside an expander (ensures it renders correctly)
                with st.expander(f"Row {i+1} - {desc[:40]}..."):
                    st.code(response.output_text, language="text")

                output_texts.append(response.output_text)
            except Exception as e:
                output_texts.append(f"ERROR: {str(e)}")

            progress.progress((i + 1) / len(df), text=f"Processed {i + 1} / {len(df)} rows")
            time.sleep(0.5)  # Rate limit friendly

        # --- Step 4: Create New Columns Based on Output ---
        output_cols = ["Product Category", "Product SubCategory", "Product Type", "Material of Construction", 
                       "Size or Dimension", "Standards", "Finish", "Miscellaneous Info", "Cautions", "Assumption Reasons"]
        parsed_outputs = {col: [] for col in output_cols}

        for text in output_texts:
            lines = text.splitlines()
            out_dict = {col: "" for col in output_cols}
            current_col = None
            for line in lines:
                line = line.strip()
                matched = False
                for col in output_cols:
                    if line.lower().startswith(col.lower() + ":"):
                        value = line.split(":", 1)[-1].strip()
                        out_dict[col] = value
                        current_col = col
                        matched = True
                        break

                if not matched and current_col:
                    # Append multiline content to the last matched column
                    out_dict[current_col] += "\n" + line

            for col in output_cols:
                parsed_outputs[col].append(out_dict[col])

        for col in output_cols:
            df[col] = parsed_outputs[col]

        # Store the processed df in session_state - ensure it's a DataFrame
        processed_df = df[[selected_col] + output_cols].copy()
        st.session_state.processed_df = processed_df  # This should be a DataFrame
        st.session_state.has_processed = True
        
        # Force a rerun to show the table properly
        st.rerun()

    # --- Always display the results section if we have processed data ---
    if st.session_state.has_processed and st.session_state.processed_df is not None:
        # --- Step 5: Editable and stable Grid ---
        st.subheader("🧾 Review and Edit AI Output")
        
        # Make sure we're working with a DataFrame - defensive programming
        if not isinstance(st.session_state.processed_df, pd.DataFrame):
            try:
                st.session_state.processed_df = pd.DataFrame(st.session_state.processed_df)
            except Exception as e:
                st.error(f"Error: The processed data is not in the correct format. {str(e)}")
                st.session_state.processed_df = None
                st.rerun()
        
        # Now safely display the data editor
        edited_df = st.data_editor(
            st.session_state.processed_df,
            num_rows="dynamic",
            use_container_width=True,
            key="editable_table",
            on_change=handle_table_edit
        )
        
        # --- Step 6: Download Final Excel ---
        st.subheader("⬇️ Download Final Excel")
        
        @st.cache_data
        def convert_df_to_excel(dataframe):
            from io import BytesIO
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                dataframe.to_excel(writer, index=False)
            return output.getvalue()
        
        # Use the session_state.processed_df directly for download
        excel_data = convert_df_to_excel(st.session_state.processed_df)
        st.download_button(
            "Download Excel with AI Output", 
            data=excel_data, 
            file_name="rfq_output.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        # Add reset button
        if st.button("Clear Results and Start Over"):
            for key in ["processed_df", "has_processed", "original_df", "selected_col"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()

else:
    st.info("Please upload an Excel file to begin.")
import streamlit as st
from copy import deepcopy
import json
import pathlib
import tempfile
import os
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from pdf2image import convert_from_path

from ocr_extractor import extract_page_json, merge_page_results
from llm_handler import LLMHandler
#from auth import start_google_login, handle_oauth_callback, get_current_user, logout
from auth import start_login, handle_oauth_callback_gen, get_current_user, logout
#from auth.manager import AuthManager

# Loading JSON Schemas:
# Scans a folder for schemaX.json.
# Loads each schema as a dictionary keyed by page number (schemas[1], schemas[2], etc.).
# Each schema defines form fields and types.
SCHEMA_DIR = "./schemas"
import sys
#print(sys.path)
schemas = {}
for fname in os.listdir(SCHEMA_DIR):
    if fname.startswith("schema") and fname.endswith(".json"):
        num = int(fname.replace("schema", "").replace(".json", ""))
        with open(os.path.join(SCHEMA_DIR, fname)) as f:
            schemas[num] = json.load(f)

# Streamlit page config & env:
#Sets title, icon, and wide layout.
#Loads environment variables from .env.
st.set_page_config(
    page_title="Handwritten Form Extractor",
    page_icon="📝",
    layout="wide",
)
load_dotenv()

# def normalize_for_ui(obj):
#     if isinstance(obj, dict) and "value" in obj:
#         return obj["value"], obj.get("description")

#     if isinstance(obj, dict) and "properties" in obj:
#         values = {}
#         descriptions = {}
#         for k, v in obj["properties"].items():
#             val, desc = normalize_for_ui(v)
#             values[k] = val
#             if desc:
#                 descriptions[k] = desc
#         return values, descriptions

#     if isinstance(obj, dict):
#         values = {}
#         descriptions = {}
#         for k, v in obj.items():
#             if k in ("type", "enum", "items", "required"):
#                 continue
#             val, desc = normalize_for_ui(v)
#             values[k] = val
#             if desc:
#                 descriptions[k] = desc
#         return values, descriptions

#     if isinstance(obj, list):
#         return obj, None

#     return obj, None

# def materialize_from_schema(schema, extracted):
#     if not isinstance(schema, dict):
#         return extracted, schema

#     # Object
#     if "properties" in schema:
#         extracted = extracted if isinstance(extracted, dict) else {}
#         out = {}
#         for key, subschema in schema["properties"].items():
#             out[key] = materialize_from_schema(
#                 subschema,
#                 extracted.get(key)
#             )
#         return out, schema

#     # Array
#     if schema.get("type") == "array":
#         return (extracted if isinstance(extracted, list) else []), schema

#     # Scalar
#     return (extracted if extracted is not None else None), schema

#Converts a schema into a Python object structure with default values.
# Handles:
# Objects → recursive dict
# Arrays → empty list
# Scalars → None or actual value
# Useful for initializing review data.
def materialize_from_schema(obj):

    if isinstance(obj, dict) and "value" in obj:
        return materialize_from_schema(obj["value"])

    if isinstance(obj, dict) and "properties" in obj:
        result = {}
        for key, val in obj["properties"].items():
            result[key] = materialize_from_schema(val)
        return result

    if isinstance(obj, dict) and obj.get("type") == "array":
        return []

    if isinstance(obj, dict):
        return {
            k: materialize_from_schema(v)
            for k, v in obj.items()
            if k not in {"type", "enum", "description", "items"}
        }

    if isinstance(obj, list):
        return [materialize_from_schema(x) for x in obj]

    return obj

# Rendering forms from schema:
# Dynamically generates Streamlit input widgets based on a JSON schema.
# Supports:
# Boolean → st.checkbox
# Integer → st.number_input
# Enum → checkboxes
# Arrays → text areas or data editor tables
# Objects → expanders
# Handles nested objects and custom behavior fields (behavioral_concerns).
# Returns a Python dict with the current user-edited values.
def render_from_schema(schema, values, key_prefix="review"):
    out = {}

    for field, field_schema in schema.get("properties", {}).items():
        label = field_schema.get("description") or field.replace("_", " ").title()
        key = f"{key_prefix}.{field}"
        value = values.get(field)
        if value == {}:
            value = None

        field_type = field_schema.get("type")
        enum = field_schema.get("enum")

        if field == "behavioral_concerns":
            st.markdown(f"### {label}")

            out[field] = {}

            for concern, concern_schema in field_schema["properties"].items():
                data = value.get(concern, {}) if isinstance(value, dict) else {}

                checked = st.checkbox(
                    concern,
                    value=data.get("checked", False),
                    key=f"{key}.{concern}.checked"
                )

                desc = ""
                freq = ""

                if checked:
                    desc = st.text_input(
                        "Describe behavior",
                        data.get("description", ""),
                        key=f"{key}.{concern}.desc"
                    )
                    freq = st.text_input(
                        "Frequency",
                        data.get("frequency", ""),
                        key=f"{key}.{concern}.freq"
                    )

                out[field][concern] = {
                    "checked": checked,
                    "description": desc,
                    "frequency": freq
                }

            return out


        elif field_type == "object":
            section_label = field_schema.get("description") or label
            with st.expander(section_label, expanded=True):
                out[field] = render_from_schema(
                    field_schema,
                    value or {},
                    key
                )

        elif field_type == "array" and field_schema.get("items", {}).get("type") == "object":
            columns = field_schema["items"].get("properties", {}).keys()
            rows = value if isinstance(value, list) else []

            if not rows:
                rows = [{col: "" for col in columns}]

            normalized_rows = []
            for row in rows:
                normalized_rows.append({
                    col: row.get(col, "") if isinstance(row, dict) else ""
                    for col in columns
                })

            st.markdown(f"**{label}**")

            edited_df = st.data_editor(
                pd.DataFrame(normalized_rows),
                num_rows="dynamic",
                use_container_width=True,
                key=key
            )

            out[field] = [
                r for r in edited_df.to_dict(orient="records")
                if any(v.strip() for v in r.values())
            ]


        elif enum:
            selected = set(value if isinstance(value, list) else ([value] if value else []))
            chosen = []

            st.markdown(f"**{label}**")

            for option in enum:
                checked = st.checkbox(
                    option,
                    value=option in selected,
                    key=f"{key}.{option}"
                )
                if checked:
                    chosen.append(option)

            out[field] = chosen

        elif field_type == "boolean":
            out[field] = st.checkbox(
                label,
                value=bool(value),
                key=key
            )

        elif field_type == "integer":
            out[field] = st.number_input(
                label,
                value=value or 0,
                step=1,
                key=key
            )
        
        elif field_type == "array":
            text = st.text_area(
                label,
                "\n".join(map(str, value or [])),
                key=key
            )
            out[field] = [v for v in text.splitlines() if v.strip()]

        else:  # string or fallback
            out[field] = st.text_input(
                label,
                "" if value is None else str(value),
                key=key
            )

    return out

# Ensures a clean session state on first run.
# Tracks PDFs, page selections, extracted data, etc.
def init_state():
    st.session_state.pdf_pages = None
    st.session_state.last_pdf = None
    st.session_state.selected_pages = set()
    st.session_state.page_order = []
    st.session_state.page_schemas = {}
    st.session_state.pages_confirmed = False
    st.session_state.schemas_confirmed = False
    st.session_state.extraction_complete = False
    st.session_state.extracted_data = None

if "initialized" not in st.session_state:
    init_state()
    st.session_state.initialized = True

#q = st.query_params
#user = None
#if "code" in q and "state" in q:
#    user = handle_oauth_callback()
#if not user:
#    user = get_current_user()
#if not user:
#    st.title("Sign in to continue")
#    st.caption("Use your Google account.")
#    if "_auth_url" not in st.session_state:
#        st.session_state["_auth_url"] = start_google_login()
#    st.link_button("Continue with Google", st.session_state["_auth_url"], type="primary")
#    st.stop()

q = st.query_params
user = None

if "code" in q and "state" in q:
    user = handle_oauth_callback_gen()

if not user:
    user = get_current_user()

if not user:
    st.title("Sign in to continue")

    # Create 3 columns: side (25%), middle (50%), side (25%)
    # This effectively makes your buttons 50% of the page width
    left_spacer, middle_column, right_spacer = st.columns([1, 2, 1])

    with left_spacer:
        # --- ROW 1: Google ---
        if "_google_auth" not in st.session_state:
            st.session_state["_google_auth"] = start_login("google")
        
        st.link_button(
            "Continue with Google",
            st.session_state["_google_auth"],
            type="primary",
            use_container_width=True  # Fills the 50% middle column
        )

        # --- ROW 2: Microsoft ---
        if "_ms_auth" not in st.session_state:
            st.session_state["_ms_auth"] = start_login("microsoft")
        
        st.link_button(
            "Continue with Microsoft",
            st.session_state["_ms_auth"],
            use_container_width=True  # Fills the 50% middle column
        )
    st.stop()

with st.sidebar:
    if user.picture:
        st.image(user.picture, width=64)
    st.markdown(f"**{user.name}**")
    st.caption(user.email)

    st.divider()

    # PDF upload & page conversion
    uploaded_pdf = st.file_uploader("📤 Upload filled PDF form", type=["pdf"])

    #if st.button("Log out"): #QC removed
        #logout()
        #st.rerun()
    if st.button("Log out"): #QC added
        AuthManager.logout()
        st.rerun()

st.title("📝 Handwritten Form Extractor")

try:
    llm = LLMHandler()
except Exception as e:
    st.error(f"Failed to initialize LLM: {e}")
    st.stop()

#Tabs: Upload / Pages / Review / Export
#Upload tab
#Pages tab
#Shows all pages as images.
#Lets user select/deselect pages.
#Confirm selection.
#Extracts data from selected pages using OCR + LLM.
if uploaded_pdf and uploaded_pdf.name != st.session_state.last_pdf:
    init_state()

    temp_pdf = pathlib.Path(f"./temp_{uploaded_pdf.name}")
    temp_pdf.write_bytes(uploaded_pdf.read())

    pages = convert_from_path(temp_pdf, dpi=150)
    st.session_state.pdf_pages = pages
    st.session_state.last_pdf = uploaded_pdf.name
    st.session_state.page_order = list(range(1, len(pages) + 1))
    st.session_state.selected_pages = set(st.session_state.page_order)

tab_upload, tab_pages, tab_review, tab_export = st.tabs([
    "📤 Upload",
    "📄 Pages & Schema",
    "✏️ Review",
    "📥 Export",
])


with tab_upload:
    if not uploaded_pdf:
        st.info("Upload a PDF to begin.")
    else:
        st.success(f"Loaded **{uploaded_pdf.name}** ({len(st.session_state.pdf_pages)} pages)")


with tab_pages:
    if not st.session_state.pdf_pages:
        st.info("Upload a PDF first.")
        st.stop()

    st.subheader("📄 Select Pages")

    pages = st.session_state.pdf_pages
    total_pages = len(pages)

    st.session_state.setdefault("selected_pages", set())
    st.session_state.setdefault("pages_confirmed", False)
    st.session_state.setdefault("extraction_complete", False)

    new_selection = set(st.session_state.selected_pages)

    col1, col2, _ = st.columns([1, 1, 6])
    with col1:
        if st.button("Select All"):
            st.session_state.selected_pages = set(range(1, total_pages + 1))
            for page_num in range(1, total_pages + 1):
                st.session_state[f"page_{page_num}"] = True
            st.session_state.pages_confirmed = False
            st.rerun()

    with col2:
        if st.button("Deselect All"):
            st.session_state.selected_pages = set()
            for page_num in range(1, total_pages + 1):
                st.session_state[f"page_{page_num}"] = False
            st.session_state.pages_confirmed = False
            st.rerun()

    cols = st.columns(3)
    for idx, page_num in enumerate(range(1, total_pages + 1)):
        with cols[idx % 3]:
            st.image(pages[page_num - 1], caption=f"Page {page_num}")
            checked = st.checkbox(
                f"Include Page {page_num}",
                value=(page_num in st.session_state.selected_pages),
                key=f"page_{page_num}",
                disabled=st.session_state.pages_confirmed,
            )
            if checked:
                new_selection.add(page_num)
            else:
                new_selection.discard(page_num)

    if not st.session_state.pages_confirmed:
        if st.button("Confirm Selected Pages", type="primary"):
            if not new_selection:
                st.warning("Select at least one page.")
                st.stop()

            st.session_state.selected_pages = new_selection
            st.session_state.pages_confirmed = True
            st.rerun()
    else:
        st.success("Pages confirmed.")

    st.divider()

    if not st.session_state.pages_confirmed:
        st.stop()

    if not st.session_state.extraction_complete:
        if st.button("🚀 Run Extraction", type="primary"):
            all_page_data = []
            progress = st.progress(0)
            status = st.empty()

            selected = sorted(st.session_state.selected_pages)

            for idx, page_num in enumerate(selected, start=1):
                status.write(f"Processing page {page_num}")
                page = pages[page_num - 1]

                schema = schemas.get(page_num)
                if not schema:
                    raise ValueError(f"No schema file found for page {page_num}")

                with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
                    page.save(tmp.name, "PNG")
                    img_bytes = open(tmp.name, "rb").read()

                page_json = extract_page_json(
                    llm,
                    img_bytes,
                    page_num,
                    json.dumps(schema),
                )

                # all_page_data.append(page_json)
                all_page_data.append({
                    "page": page_num,
                    "data": page_json
                })
                progress.progress(idx / len(selected))

            # st.session_state.extracted_data = merge_page_results(all_page_data)
            st.session_state.extracted_data = {
                item["page"]: item["data"]
                for item in all_page_data
            }
            st.session_state.extraction_complete = True
            st.success("Extraction complete.")


#Review tab
#Allows editing the extracted data.
#Uses render_from_schema to generate interactive forms.
#Supports:
#Nested objects
#Lists
#Behavioral concerns (checkbox + description/frequency)
#Can confirm changes or apply to final output.
with tab_review:
    if not st.session_state.get("extraction_complete"):
        st.info("Run extraction first.")
        st.stop()

    st.header("✏️ Review Extracted Form Data")

    # if "review_data" not in st.session_state:
    #     full_data = {}

    #     selected_pages = st.session_state.selected_pages

    #     # for page_num in sorted(selected_pages):
    #     #     schema = schemas[page_num]
    #     #     extracted = st.session_state.extracted_data 
    #     #     st.success(extracted)
    #     #     print(extracted)
    #     #     page_data= materialize_from_schema(extracted)
    #     #     full_data.update(page_data)

    #     st.session_state.review_data = full_data

    if "review_data" not in st.session_state:
        st.session_state.review_data = {
            page_num: materialize_from_schema(page_data)
            for page_num, page_data in st.session_state.extracted_data.items()
        }
    
    review_data = st.session_state.review_data

    available_pages = sorted(review_data.keys())

    selected_page = st.selectbox(
        "Select page to review",
        available_pages,
        format_func=lambda p: f"{p}"
    )

    def pretty_label(label: str) -> str:
        return label.replace("_", " ").strip().title()

    # def render_scalar(label, value, schema, key):
        # field_type = schema.get("type")

        # if field_type == "boolean":
        #     return st.checkbox(label, value=value or False, key=key)

        # if field_type == "integer":
        #     return st.number_input(label, value=value or 0, step=1, key=key)

        # if "enum" in schema:
        #     if schema.get("type") == "array":
        #         return st.multiselect(label, schema["enum"], default=value or [], key=key)
        #     return st.selectbox(
        #         label,
        #         schema["enum"],
        #         index=schema["enum"].index(value) if value in schema["enum"] else 0,
        #         key=key
        #     )

        # return st.text_input(label, value="" if value is None else str(value), key=key)

    # def render_any(label, value, schema, key, depth=0):
        # if isinstance(value, dict):
        #     if depth == 0:
        #         st.subheader(label)
        #     elif depth == 1:
        #         st.markdown(f"**{label}**")
        #     else:
        #         st.markdown(f"*{label}*")

        #     out = {}
        #     for k, v in value.items():
        #         field_schema = schema.get("properties", {}).get(k, {})
        #         out[k] = render_any(
        #             pretty_label(k),
        #             v,
        #             field_schema,
        #             f"{key}.{k}",
        #             depth + 1
        #         )
        #     return out

        # if isinstance(value, list):
        #     if schema.get("type") == "array" and "enum" in schema:
        #         return st.multiselect(
        #             label,
        #             schema["enum"],
        #             default=value,
        #             key=key
        #         )
        #     return st.text_area(
        #         label,
        #         value="\n".join(map(str, value)),
        #         key=key
        #     ).splitlines()

        # return render_scalar(label, value, schema, key)

    edited_output = {}

    # for section in review_data.keys():
        # Temporary debug line
        #print(f"DEBUG: Processing {section}, value is: {edited_output[section]}")
        
    page_num = selected_page

    edited_output = {}
    edited_output[page_num] = render_from_schema(
        schemas[page_num],
        review_data[page_num],
        key_prefix=f"review.page{page_num}"
    )


    col1, col2 = st.columns(2)

    with col1:
        if st.button("✅Confirm Changes"):  #💾 Save Changes"):
            st.session_state.review_data = edited_output
            st.success("Review changes saved.")

    with col2:
        if st.button("✅ Apply to Final Output"):
            st.session_state.extracted_data = deepcopy(st.session_state.review_data)
            st.success("Changes applied to extracted data.")


#Export tab
#Flattens extracted data to match Therap Excel schema.
#Uses mapping JSON (field_mapping.json) to map fields.
#Generates two Excel files:
#Import-ready
#Extra fields
#Provides Streamlit download buttons.
with tab_export:
    if not st.session_state.extraction_complete:
        st.info("Complete extraction first.")
        st.stop()

    st.subheader("📥 Export")

    if st.button("Send to Therap"):
        base_name = st.session_state.get("base_name", "export")
        edited_data = st.session_state.get("extracted_data") or {}
        if not edited_data:
            st.info("No reviewed data available to export.")
            st.stop()


        with open("field_mapping.json", "r") as f:
            mapping_json = json.load(f)

        mapping = mapping_json.get("mappings", {})
        reverse_map = {v: k for k, v in mapping.items() if v}

        def flatten_json(data, parent_key="", sep="."):
            items = {}
            for k, v in data.items():
                new_key = f"{parent_key}{sep}{k}" if parent_key else k
                if isinstance(v, dict):
                    items.update(flatten_json(v, new_key, sep))
                else:
                    items[new_key] = v
            return items

        merged = {}
        for page_data in edited_data.values():
            merged.update(page_data)

        flat_data = flatten_json(merged)
        extracted_df = pd.DataFrame([flat_data])

        idf_df = pd.read_excel("IDF_Import_ProviderExcel_TOT-AZ_20251019.xlsx") #idf_path)
        idf_cols = list(idf_df.columns)

        official_df = pd.DataFrame(columns=idf_cols)

        for col in idf_cols:
            source_key = reverse_map.get(col)
            if source_key and source_key in extracted_df.columns:
                official_df[col] = extracted_df[source_key]
            else:
                official_df[col] = ""

        mapped_extract_cols = set(reverse_map.values())
        extra_cols = [c for c in extracted_df.columns if c not in mapped_extract_cols]
        extra_df = extracted_df[extra_cols] if extra_cols else pd.DataFrame()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        official_file = f"./{base_name}_import_ready_{ts}.xlsx"
        extra_file = f"./{base_name}_extra_fields_{ts}.xlsx"

        official_df.to_excel(official_file, index=False)

        if not extra_df.empty:
            extra_df.to_excel(extra_file, index=False)

        st.success("Files generated successfully")

        with open(official_file, "rb") as f:
            st.download_button(
                "⬇️ Download Import-Ready Excel (Therap Schema)",
                f,
                file_name=os.path.basename(official_file),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        if not extra_df.empty:
            with open(extra_file, "rb") as f:
                st.download_button(
                    "⬇️ Download Extra Fields Excel",
                    f,
                    file_name=os.path.basename(extra_file),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

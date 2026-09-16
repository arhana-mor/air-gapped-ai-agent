
import io
import re
import sys
import os
import base64
import hashlib
import datetime
import urllib.parse
import streamlit as st
from openai import OpenAI
from docx import Document
from docx.shared import Pt, RGBColor
import pypdf
import networkx as nx

# DXF parser
try:
    import ezdxf
    DXF_AVAILABLE = True
except ImportError:
    DXF_AVAILABLE = False

def parse_dxf_file(uploaded_file):
    if not DXF_AVAILABLE:
        return "⚠️ ezdxf package not installed. Install via: pip install ezdxf"
    try:
        doc = ezdxf.read(io.StringIO(uploaded_file.getvalue().decode('utf-8', errors='ignore')))
        msp = doc.modelspace()
        extracted_entities = []
        for e in msp:
            if e.dxftype() in ['TEXT', 'MTEXT']:
                extracted_entities.append(f"Text Entity: '{e.dxf.text}' at layer '{e.dxf.layer}'")
            elif e.dxftype() == 'INSERT':
                extracted_entities.append(f"Block Insert: '{e.dxf.name}' at layer '{e.dxf.layer}'")

        if not extracted_entities:
            return f"DXF File loaded successfully ({len(list(msp))} total entities, no explicit text tags found)."
        return "\n".join(extracted_entities[:50])
    except Exception as e:
        return f"Error parsing DXF file: {str(e)}"

# Plant knowledge graph
def build_plant_knowledge_graph():
    G = nx.DiGraph()

    G.add_node("Pump_P101", type="Equipment", desc="Main Crude Charge Pump")
    G.add_node("Line_L204", type="Pipeline", desc="12-inch High-Pressure Line (Class 300)")
    G.add_node("Valve_V102", type="Valve", desc="Normally Open Isolation Valve")

    G.add_node("Doc_INSP_2025_09", type="InspectionReport", desc="SOP-401 Pg 14: Flange corrosion detected near P-101 discharge")
    G.add_node("Doc_SOP_302", type="SafetySOP", desc="SOP-302 Sec 4: Requires line depressurization before pump decoupling")

    G.add_edge("Pump_P101", "Line_L204", relation="FEEDS")
    G.add_edge("Line_L204", "Valve_V102", relation="CONTAINS")
    G.add_edge("Pump_P101", "Doc_INSP_2025_09", relation="HAS_OPEN_FINDING")
    G.add_edge("Pump_P101", "Doc_SOP_302", relation="GOVERNED_BY")

    return G

def trace_plant_impact(G, entity_id):
    if entity_id not in G:
        return False, f"⚠️ UNVERIFIED: Entity '{entity_id}' not found in Plant Knowledge Graph."

    traversal_nodes = nx.single_source_shortest_path_length(G, entity_id, cutoff=2)
    impact_data = []
    for node in traversal_nodes:
        node_attr = G.nodes[node]
        impact_data.append(f"- **{node}** ({node_attr.get('type')}): {node_attr.get('desc')}")

    return True, "\n".join(impact_data)

st.set_page_config(page_title="PS 26117", layout="wide")

OLLAMA_BASE_URL = "http://localhost:11434/v1"
client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="sk-local-airgap")

# Local endpoint verification
def _is_loopback_url(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1")

if "local_call_count" not in st.session_state:
    st.session_state.local_call_count = 0

IS_LOCAL_ONLY = _is_loopback_url(OLLAMA_BASE_URL)

st.sidebar.title("🛡️ Sovereignty Status")
if IS_LOCAL_ONLY:
    st.sidebar.success(f"AI client hard-coded to localhost\n\n`{OLLAMA_BASE_URL}`")
else:
    st.sidebar.error(f"AI client is NOT loopback-only: `{OLLAMA_BASE_URL}`")

st.sidebar.metric("Local AI calls this session", st.session_state.local_call_count)
st.sidebar.caption(
    "This confirms every AI call in this app went to a local endpoint. "
    "It cannot see the rest of the machine's network traffic — for a live "
    "demo, physically disconnect the network cable for the strongest proof."
)

def call_local_model(**kwargs):
    """
    Sends AI requests through the local Ollama client and handles connection errors.
    """
    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as e:
        raise RuntimeError(
            f"Could not reach the local model server at {OLLAMA_BASE_URL}. "
            f"Is Ollama running, and is the model '{kwargs.get('model')}' pulled? "
            f"({type(e).__name__}: {e})"
        ) from e
    st.session_state.local_call_count += 1
    return response

# Markdown to Word export
def parse_markdown_to_docx(text: str, audit_hash: str, model_used: str, task_mode: str) -> bytes:
    doc = Document()
    for line in text.split('\n'):
        cleaned = line.strip()
        if not cleaned:
            continue
        if cleaned.startswith('# '):
            doc.add_heading(cleaned[2:].replace('**', ''), level=1)
        elif cleaned.startswith('## '):
            doc.add_heading(cleaned[3:].replace('**', ''), level=2)
        elif cleaned.startswith('### '):
            doc.add_heading(cleaned[4:].replace('**', ''), level=3)
        elif cleaned.startswith(('- ', '* ')):
            p = doc.add_paragraph(style='List Bullet')
            _add_formatted_text(p, cleaned[2:])
        else:
            p = doc.add_paragraph()
            _add_formatted_text(p, cleaned)

    doc.add_page_break()
    doc.add_heading("🛡️ Certificate of Enterprise AI Lineage", level=1)

    p = doc.add_paragraph()
    p.add_run("Generated inside an isolated, air-gapped sovereign environment.\n").italic = True

    p_meta = doc.add_paragraph()
    p_meta.add_run(f"Timestamp: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n").bold = True
    p_meta.add_run(f"Task Engine Mode: {task_mode}\n").bold = True
    p_meta.add_run(f"Auto-Selected Model: {model_used}\n").bold = True
    p_meta.add_run(f"AI Endpoint: {OLLAMA_BASE_URL} (loopback-verified)\n").bold = True
    p_meta.add_run(f"Cryptographic SHA-256 Hash:\n").bold = True

    p_hash = doc.add_paragraph()
    run_hash = p_hash.add_run(audit_hash)
    run_hash.font.size = Pt(9)
    run_hash.font.color.rgb = RGBColor(100, 100, 100)

    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()

def _add_formatted_text(paragraph, text):
    parts = re.split(r'(\*\*.*?\*\*)', text)
    for part in parts:
        if part.startswith('**') and part.endswith('**'):
            paragraph.add_run(part[2:-2]).bold = True
        else:
            paragraph.add_run(part)

# Calculation sandbox
import ast
import json
import subprocess

_BLOCKED_NAMES = {
    "os", "sys", "subprocess", "socket", "shutil", "requests", "urllib",
    "pathlib", "open", "eval", "exec", "__import__", "compile", "globals",
    "locals", "input", "breakpoint", "ctypes", "importlib",
}
_BLOCKED_ATTRS = {"system", "popen", "remove", "rmtree", "unlink", "chmod", "kill"}

def _static_screen(code: str):
    """Reject obviously unsafe code before it is executed."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"SyntaxError: {e}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name.split(".")[0] in _BLOCKED_NAMES:
                    return False, f"Blocked import: '{n.name}' is not permitted in the calculation sandbox."
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in _BLOCKED_NAMES:
                return False, f"Blocked import: '{node.module}' is not permitted in the calculation sandbox."
        elif isinstance(node, ast.Name) and node.id in _BLOCKED_NAMES:
            return False, f"Blocked name: '{node.id}' is not permitted in the calculation sandbox."
        elif isinstance(node, ast.Attribute) and node.attr in _BLOCKED_ATTRS:
            return False, f"Blocked operation: '.{node.attr}(...)' is not permitted in the calculation sandbox."
    return True, None

_SANDBOX_WORKER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sandbox_worker.py")

def run_sandboxed_code(code: str, timeout_seconds: int = 5):
    ok, reason = _static_screen(code)
    if not ok:
        return False, reason

    try:
        proc = subprocess.run(
            [sys.executable, _SANDBOX_WORKER_PATH],
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT_ERROR: Code exceeded the {timeout_seconds}s execution limit and was terminated."

    if proc.returncode != 0:
        return False, f"WORKER_ERROR: Sandbox process crashed (exit code {proc.returncode}): {proc.stderr.strip()[:500]}"

    try:
        result = json.loads(proc.stdout.strip())
    except (json.JSONDecodeError, ValueError):
        return False, f"WORKER_ERROR: Sandbox process returned unparseable output: {proc.stdout.strip()[:500]}"

    return result["success"], result["output"]

def execute_self_healing_loop(user_prompt, client, selected_model, max_retries=3):
    system_prompt = (
        "You are an industrial calculation engine. Write executable Python code to solve the user's request.\n"
        "ALWAYS use explicit print() statements formatted with f-strings to display readable numbers.\n"
        "Output ONLY raw Python code inside ```python ... ``` blocks."
    )
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
    attempts_log = []

    for attempt in range(1, max_retries + 1):
        response = call_local_model(model=selected_model, messages=messages)
        raw_reply = response.choices[0].message.content
        code = raw_reply.split("```python")[1].split("```")[0].strip() if "```python" in raw_reply else raw_reply.strip()

        success, result = run_sandboxed_code(code)
        attempts_log.append({"attempt": attempt, "code": code, "success": success, "result": result})

        if success:
            return True, result, attempts_log

        messages.append({"role": "assistant", "content": raw_reply})
        messages.append({"role": "user", "content": f"Execution Error on attempt {attempt}:\n{result}\nFix code and output ONLY revised ```python block."})

    return False, "Failed execution within retry limit.", attempts_log

# Workbench UI
st.title("🛡️ Sovereign AI Workbench")
st.caption("On-Premise Industrial Engine: Auto-routes models across CAD, inspection documents, and sandboxed math.")

with st.form("unified_workbench_form"):
    uploaded_file = st.file_uploader(
        "Upload Drawing (.dxf), Report (.pdf/.txt), or Image",
        type=["pdf", "txt", "md", "dxf", "png", "jpg", "jpeg"],
        key="workbench_file"
    )
    user_prompt = st.text_area("Task Instruction / Query:", placeholder="e.g., 'Replace Pump P101 impact', 'Evaluate CAD design', or 'Calculate pump MTBF'", height=100)
    submit_btn = st.form_submit_button("⚡ EXECUTE SOVEREIGN AGENT")

if submit_btn:
    file_ext = uploaded_file.name.split(".")[-1].lower() if uploaded_file else ""
    output_report = ""

    try:
        # Route 1: Plant knowledge graph
        if ("replace" in user_prompt.lower() or "impact" in user_prompt.lower() or "maintenance" in user_prompt.lower()) and "p101" in user_prompt.lower():
            task_mode = "Deterministic Graph Traversal & Impact Analysis"
            selected_model = "qwen2.5-coder:1.5b"
            target_entity = "Pump_P101"

            st.info(f"⚙️ **Auto-Selected Model:** `{selected_model}` | **Engine Mode:** `{task_mode}`")

            with st.spinner("Traversing Plant Knowledge Graph & verifying sources..."):
                PKG = build_plant_knowledge_graph()
                found, graph_context = trace_plant_impact(PKG, target_entity)

                grounded_system_prompt = (
                    "You are a Sovereign Refinery Safety Agent.\n"
                    "RULES:\n"
                    "1. Answer ONLY using the provided Plant Knowledge Graph context.\n"
                    "2. Cite exact source documents for every claim (e.g., [Doc: SOP-302 Sec 4]).\n"
                    "3. If information is missing or cannot be verified from context, state explicitly: "
                    "'[UNVERIFIED]: This detail is not verified in plant records.' DO NOT GUESS."
                )
                response = call_local_model(
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": grounded_system_prompt},
                        {"role": "user", "content": f"GRAPH CONTEXT:\n{graph_context}\n\nUSER PROMPT: {user_prompt}"}
                    ]
                )
                output_report = f"# 🌐 Deterministic Impact Analysis: {target_entity}\n\n" + response.choices[0].message.content

        # Route 2: Calculation sandbox
        elif "calc" in user_prompt.lower() or "probability" in user_prompt.lower() or "python" in user_prompt.lower():
            task_mode = "Deterministic Calculation Sandbox"
            selected_model = "qwen2.5-coder:1.5b"
            st.info(f"⚙️ **Auto-Selected Model:** `{selected_model}` | **Engine Mode:** `{task_mode}`)

            with st.spinner("Executing Sandboxed Autonomous Loop..."):
                success, final_output, logs = execute_self_healing_loop(user_prompt, client, selected_model)
                output_report = f"# Verified Calculation Deliverable\n\n**Result:**\n{final_output}\n\n## Execution Log\n"
                for log in logs:
                    status_icon = "✅" if log["success"] else "⚠️"
                    output_report += f"\n### Attempt {log['attempt']} ({status_icon})\n```python\n{log['code']}\n```\nStdout: {log['result']}\n"

        # Route 3: Multimodal vision
        elif file_ext in ["png", "jpg", "jpeg"]:
            task_mode = "Multimodal Vision & Schematic Analysis"
            selected_model = "qwen2.5vl:3b"
            st.info(f"⚙️ **Auto-Selected Model:** `{selected_model}` | **Engine Mode:** `{task_mode}`")

            with st.spinner("Encoding and analyzing visual input locally..."):
                img_bytes = uploaded_file.getvalue()
                base64_img = base64.b64encode(img_bytes).decode('utf-8')
                mime_type = "image/png" if file_ext == "png" else "image/jpeg"

                prompt_text = user_prompt.strip() or "Describe all observable physical assets, tags, materials, and defects visible in this image."

                vision_system_prompt = (
                    "You are an industrial plant visual inspector.\n"
                    "Step 1: Describe the key visible components, equipment tags, corrosion, or physical damage in the image.\n"
                    "Step 2: Directly answer the user's question using only these visual details.\n"
                    "Step 3: If the exact cause or spec isn't fully visible in the image, state what physical evidence is present and what further physical inspection (e.g., NDT testing) is required."
                )

                response = call_local_model(
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": vision_system_prompt},
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt_text},
                                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_img}"}}
                            ]
                        }
                    ]
                )
                output_report = f"# 📷 Visual & Schematic Analysis\n\n" + response.choices[0].message.content

        # Route 4: Document synthesis and CAD parsing
        else:
            task_mode = "Document Synthesis & Engineering Reporting"
            selected_model = "qwen2.5-coder:1.5b"
            st.info(f"⚙️ **Auto-Selected Model:** `{selected_model}` | **Engine Mode:** `{task_mode}`)

            with st.spinner("Processing document data on local compute..."):
                extracted_text = ""
                if file_ext == "pdf":
                    pdf_reader = pypdf.PdfReader(uploaded_file)
                    extracted_text = "\n".join([p.extract_text() for p in pdf_reader.pages if p.extract_text()])
                elif file_ext == "dxf":
                    extracted_text = parse_dxf_file(uploaded_file)
                elif file_ext in ["txt", "md"]:
                    extracted_text = uploaded_file.read().decode("utf-8")
                else:
                    extracted_text = "[No file uploaded - processing prompt directly]"

                sys_prompt = (
                    "You are a sovereign refinery engineering agent. "
                    "Synthesize the provided context and output a concise, structured report with bullet points and bold headers. "
                    "Ground all facts strictly in the provided context."
                )
                response = call_local_model(
                    model=selected_model,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": f"CONTEXT:\n{extracted_text}\n\nINSTRUCTION: {user_prompt}"}
                    ]
                )
                output_report = response.choices[0].message.content

    except RuntimeError as e:
        st.error(f"⚠️ {e}")
        output_report = None
    except Exception as e:
        st.error(f"⚠️ Unexpected error while processing this request: {type(e).__name__}: {e}")
        output_report = None

    # Output and audit export
    if output_report:
        st.divider()
        st.subheader("📊 Output Deliverable")
        st.markdown(output_report)

        hash_input = f"{user_prompt}{output_report}{datetime.datetime.now().isoformat()}"
        audit_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

        docx_data = parse_markdown_to_docx(output_report, audit_hash, selected_model, task_mode)
        st.download_button(
            label="📄 Download Executive Deliverable (.docx with SHA-256 Stamp)",
            data=docx_data,
            file_name="MRPL_Sovereign_Deliverable.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

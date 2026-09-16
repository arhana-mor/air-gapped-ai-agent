# Air-Gapped AI Agent

An ongoing project for building an offline AI agent for engineering and industrial use cases. The system runs open-weight language and vision models locally through Ollama and combines document processing, visual analysis, plant knowledge graphs, and sandboxed calculations in a single workflow.

## What It Does

- Runs AI models locally through **Ollama** without external AI APIs.
- Routes tasks between language and vision models based on the input.
- Processes text and images and performs engineering calculations.
- Uses a plant knowledge graph to connect equipment with pipelines, valves, inspections, and safety documents. Current data is comprised of hardcoded values.
- Generates and executes Python calculations in a separate sandboxed subprocess.
- Sends execution errors back to the local model for correction and retry.
- Generates structured engineering reports and exports them as Word documents.
- Uses SHA-256 hashing to create an audit stamp for generated deliverables.
- Marks information as unverified when it cannot be supported by the available plant context.

## Technologies Used

- **Python** : Application logic, document processing, sandbox execution, knowledge graph, and reporting.
- **Ollama** : Local execution of open-weight AI models.
- **Qwen2.5-Coder:1.5B** : Calculation code generation, error correction, and engineering report generation.
- **Qwen2.5-VL:3B** : Intended for analysing scanned blueprints, handwritten notes, engineering diagrams, and other images; blueprint-specific logic is still being implemented.
- **Streamlit** — User interface and AI workbench.
- **OpenAI Python SDK** — Sends requests to Ollama through its OpenAI-compatible API.
- **NetworkX** — Plant knowledge graph construction and traversal.
- **PyPDF** — PDF text extraction.
- **ezdxf** — DXF/CAD parsing.
- **python-docx** — Word report generation.

## System Architecture

```text
                         User Input
                             |
                             v
                    +----------------+
                    |   Streamlit    |
                    |   Workbench    |
                    +----------------+
                             |
                             v
                       Task Routing
                    /       |        \
                   /        |         \
                  v         v          v
             Documents    Images   Calculations
                  |         |          |
                  v         v          v
             Qwen2.5-     Qwen2.5-   Qwen2.5-
              Coder         VL        Coder
                  \         |          /
                   \        |         /
                    v       v        v
                         Ollama
                            |
                            v
                    Local Processing
                            |
                            v
                       Output Report
                            |
                            v
                       SHA-256 Hash
```

AI requests are sent to the local Ollama endpoint through the OpenAI-compatible Python SDK.

## Key Workflows

### Plant Knowledge Graph

The application maintains relationships between plant equipment and supporting engineering records.

```text
Pump P101
   |
   +---- FEEDS ----> Line L204
   |
   +---- HAS OPEN FINDING ----> Inspection Report
   |
   +---- GOVERNED BY ----> Safety SOP
```

For maintenance or impact queries, the application performs graph traversal and provides the resulting plant context to the local model. The model is instructed to distinguish verified information from information that is not available in the plant records.

### Calculation Sandbox

For calculation requests, Qwen2.5-Coder generates Python code. The application:

1. Screens the code using Python AST.
2. Blocks restricted imports and operations.
3. Runs the code in a separate subprocess.
4. Applies an execution timeout.
5. Captures the result or error.
6. Sends execution errors back to the model for another attempt.

### Document & Visual Processing

The application supports engineering inputs such as:

- PDF reports
- TXT and Markdown files
- DXF/CAD files
- Scanned blueprints
- Engineering diagrams
- Handwritten notes
- Equipment images

Text-based engineering material is processed with Qwen2.5-Coder, while visual inputs are handled by Qwen2.5-VL.

## Reliability Approach

The project is being developed around **grounded and locally processed outputs**.

For plant and document workflows, responses are based on the context provided to the model. When required information is not available, the system is designed to identify it as unverified rather than generate an unsupported answer.

Calculation outputs are based on actual sandbox execution rather than model-generated numbers alone.

## Report Export

Generated reports can be exported as Word documents containing:

- Report content
- Task mode
- Selected model
- Local AI endpoint
- Timestamp
- SHA-256 audit hash

## Project Structure

```text
air-gapped-ai-agent/
├── sovereign_workbench.py
├── sandbox_worker.py
├── requirements.txt
└── README.md
```

## Project Status

**Ongoing**

The core local AI workflow, model routing, plant knowledge graph, calculation sandbox, document processing, visual analysis, and report export are being developed and tested.

Future development will focus on expanding engineering workflows, improving validation, strengthening sandbox controls, and increasing the range of supported plant data.

## Scope

This is an engineering-focused AI application and demonstration environment, not a certified industrial safety system or production deployment.

Example plant records, equipment identifiers, engineering documents, and other data used in the project are demonstration data.

## Author

**Arhana Mor**

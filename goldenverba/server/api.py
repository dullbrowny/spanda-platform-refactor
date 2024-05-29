from fastapi import FastAPI, WebSocket, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from ollama import chat as ollama_chat
from httpx import AsyncClient
import asyncio
import json
import httpx


import os
from pathlib import Path

from dotenv import load_dotenv
from starlette.websockets import WebSocketDisconnect
from wasabi import msg  # type: ignore[import]
import time
from goldenverba.server.bitsp import(
    ollama_afe,
    ollama_aga,
    ollama_aqg
)
import logging
from goldenverba import verba_manager
from goldenverba.server.types import (
    ResetPayload,
    ConfigPayload,
    QueryPayload,
    GeneratePayload,
    GetDocumentPayload,
    SearchQueryPayload,
    ImportPayload,
    QueryRequest
)
from goldenverba.server.util import get_config, set_config, setup_managers
logger = logging.getLogger("API")
load_dotenv()

# Check if runs in production
production_key = os.environ.get("VERBA_PRODUCTION", "")
tag = os.environ.get("VERBA_GOOGLE_TAG", "")
if production_key == "True":
    msg.info("API runs in Production Mode")
    production = True
else:
    production = False

manager = verba_manager.VerbaManager()
setup_managers(manager)

# FastAPI App
app = FastAPI()

origins = [
    "http://localhost:3000",
    "https://verba-golden-ragtriever.onrender.com",
    "http://localhost:8000",
    "http://localhost:1511",
    "http://localhost:1511/courses/s24/sample/gradingAssistant",
]

# Add middleware for handling Cross Origin Resource Sharing (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent

# Serve the assets (JS, CSS, images, etc.)
app.mount(
    "/static/_next",
    StaticFiles(directory=BASE_DIR / "frontend/out/_next"),
    name="next-assets",
)

# Serve the main page and other static files
app.mount("/static", StaticFiles(directory=BASE_DIR / "frontend/out"), name="app")


@app.get("/")
@app.head("/")
async def serve_frontend():
    return FileResponse(os.path.join(BASE_DIR, "frontend/out/index.html"))

### GET

# Define health check endpoint
@app.get("/api/health")
async def health_check():
    try:
        if manager.client.is_ready():
            return JSONResponse(
                content={"message": "Alive!", "production": production, "gtag": tag}
            )
        else:
            return JSONResponse(
                content={
                    "message": "Database not ready!",
                    "production": production,
                    "gtag": tag,
                },
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
    except Exception as e:
        msg.fail(f"Healthcheck failed with {str(e)}")
        return JSONResponse(
            content={
                "message": f"Healthcheck failed with {str(e)}",
                "production": production,
                "gtag": tag,
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

# Get Status meta data
@app.get("/api/get_status")
async def get_status():
    try:
        schemas = manager.get_schemas()
        sorted_schemas = dict(
            sorted(schemas.items(), key=lambda item: item[1], reverse=True)
        )

        sorted_libraries = dict(
            sorted(
                manager.installed_libraries.items(),
                key=lambda item: (not item[1], item[0]),
            )
        )
        sorted_variables = dict(
            sorted(
                manager.environment_variables.items(),
                key=lambda item: (not item[1], item[0]),
            )
        )

        data = {
            "type": manager.weaviate_type,
            "libraries": sorted_libraries,
            "variables": sorted_variables,
            "schemas": sorted_schemas,
            "error": "",
        }

        msg.info("Status Retrieved")
        return JSONResponse(content=data)
    except Exception as e:
        data = {
            "type": "",
            "libraries": {},
            "variables": {},
            "schemas": {},
            "error": f"Status retrieval failed: {str(e)}",
        }
        msg.fail(f"Status retrieval failed: {str(e)}")
        return JSONResponse(content=data)

# Get Configuration
@app.get("/api/config")
async def retrieve_config():
    try:
        config = get_config(manager)
        msg.info("Config Retrieved")
        return JSONResponse(status_code=200, content={"data": config, "error": ""})

    except Exception as e:
        msg.warn(f"Could not retrieve configuration: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "data": {},
                "error": f"Could not retrieve configuration: {str(e)}",
            },
        )

### WEBSOCKETS

@app.websocket("/ws/generate_stream")
async def websocket_generate_stream(websocket: WebSocket):
    await websocket.accept()
    while True:  # Start a loop to keep the connection alive.
        try:
            data = await websocket.receive_text()
            # Parse and validate the JSON string using Pydantic model
            payload = GeneratePayload.model_validate_json(data)
            msg.good(f"Received generate stream call for {payload.query}")
            full_text = ""
            async for chunk in manager.generate_stream_answer(
                [payload.query], [payload.context], payload.conversation
            ):
                full_text += chunk["message"]
                if chunk["finish_reason"] == "stop":
                    chunk["full_text"] = full_text
                await websocket.send_json(chunk)

        except WebSocketDisconnect:
            msg.warn("WebSocket connection closed by client.")
            break  # Break out of the loop when the client disconnects

        except Exception as e:
            msg.fail(f"WebSocket Error: {str(e)}")
            await websocket.send_json(
                {"message": e, "finish_reason": "stop", "full_text": str(e)}
            )
        msg.good("Succesfully streamed answer")

### POST

# Reset Verba
@app.post("/api/reset")
async def reset_verba(payload: ResetPayload):
    if production:
        return JSONResponse(status_code=200, content={})

    try:
        if payload.resetMode == "VERBA":
            manager.reset()
        elif payload.resetMode == "DOCUMENTS":
            manager.reset_documents()
        elif payload.resetMode == "CACHE":
            manager.reset_cache()
        elif payload.resetMode == "SUGGESTIONS":
            manager.reset_suggestion()
        elif payload.resetMode == "CONFIG":
            manager.reset_config()

        msg.info(f"Resetting Verba ({payload.resetMode})")

    except Exception as e:
        msg.warn(f"Failed to reset Verba {str(e)}")

    return JSONResponse(status_code=200, content={})

# Receive query and return chunks and query answer
@app.post("/api/import")
async def import_data(payload: ImportPayload):

    logging = []

    if production:
        logging.append(
            {"type": "ERROR", "message": "Can't import when in production mode"}
        )
        return JSONResponse(
            content={
                "logging": logging,
            }
        )

    try:
        set_config(manager, payload.config)
        documents, logging = manager.import_data(
            payload.data, payload.textValues, logging
        )

        return JSONResponse(
            content={
                "logging": logging,
            }
        )

    except Exception as e:
        logging.append({"type": "ERROR", "message": str(e)})
        return JSONResponse(
            content={
                "logging": logging,
            }
        )

@app.post("/api/set_config")
async def update_config(payload: ConfigPayload):

    if production:
        return JSONResponse(
            content={
                "status": "200",
                "status_msg": "Config can't be updated in Production Mode",
            }
        )

    try:
        set_config(manager, payload.config)
    except Exception as e:
        msg.warn(f"Failed to set new Config {str(e)}")

    return JSONResponse(
        content={
            "status": "200",
            "status_msg": "Config Updated",
        }
    )

# Receive query and return chunks and query answer
@app.post("/api/query")
async def query(payload: QueryPayload):
    msg.good(f"Received query: {payload.query}")
    start_time = time.time()  # Start timing
    try:
        print("test1")
        chunks, context = manager.retrieve_chunks([payload.query])

        retrieved_chunks = [
            {
                "text": chunk.text,
                "doc_name": chunk.doc_name,
                "chunk_id": chunk.chunk_id,
                "doc_uuid": chunk.doc_uuid,
                "doc_type": chunk.doc_type,
                "score": chunk.score,
            }
            for chunk in chunks
        ]
        print(retrieved_chunks)
        elapsed_time = round(time.time() - start_time, 2)  # Calculate elapsed time
        msg.good(f"Succesfully processed query: {payload.query} in {elapsed_time}s")

        if len(chunks) == 0:
            return JSONResponse(
                content={
                    "chunks": [],
                    "took": 0,
                    "context": "",
                    "error": "No Chunks Available",
                }
            )

        return JSONResponse(
            content={
                "error": "",
                "chunks": retrieved_chunks,
                "context": context,
                "took": elapsed_time,
            }
        )

    except Exception as e:
        msg.warn(f"Query failed: {str(e)}")
        return JSONResponse(
            content={
                    "chunks": [],
                    "took": 0,
                    "context": "",
                    "error": f"Something went wrong: {str(e)}",
            }
        )

# Retrieve auto complete suggestions based on user input
@app.post("/api/suggestions")
async def suggestions(payload: QueryPayload):
    try:
        suggestions = manager.get_suggestions(payload.query)

        return JSONResponse(
            content={
                "suggestions": suggestions,
            }
        )
    except Exception:
        return JSONResponse(
            content={
                "suggestions": [],
            }
        )

# Retrieve specific document based on UUID
@app.post("/api/get_document")
async def get_document(payload: GetDocumentPayload):
    # TODO Standarize Document Creation
    msg.info(f"Document ID received: {payload.document_id}")

    try:
        document = manager.retrieve_document(payload.document_id)
        document_properties = document.get("properties", {})
        document_obj = {
            "class": document.get("class", "No Class"),
            "id": document.get("id", payload.document_id),
            "chunks": document_properties.get("chunk_count", 0),
            "link": document_properties.get("doc_link", ""),
            "name": document_properties.get("doc_name", "No name"),
            "type": document_properties.get("doc_type", "No type"),
            "text": document_properties.get("text", "No text"),
            "timestamp": document_properties.get("timestamp", ""),
        }

        msg.good(f"Succesfully retrieved document: {payload.document_id}")
        return JSONResponse(
            content={
                "error": "",
                "document": document_obj,
            }
        )
    except Exception as e:
        msg.fail(f"Document retrieval failed: {str(e)}")
        return JSONResponse(
            content={
                "error": str(e),
                "document": None,
            }
        )

## Retrieve and search documents imported to Weaviate
@app.post("/api/get_all_documents")
async def get_all_documents(payload: SearchQueryPayload):
    # TODO Standarize Document Creation
    msg.info("Get all documents request received")
    start_time = time.time()  # Start timing

    try:
        if payload.query == "":
            documents = manager.retrieve_all_documents(
                payload.doc_type, payload.page, payload.pageSize
            )
        else:
            documents = manager.search_documents(
                payload.query, payload.doc_type, payload.page, payload.pageSize
            )

        if not documents:
            return JSONResponse(
                content={
                    "documents": [],
                    "doc_types": [],
                    "current_embedder": manager.embedder_manager.selected_embedder,
                    "error": f"No Results found!",
                    "took": 0,
                }
            )

        documents_obj = []
        for document in documents:

            _additional = document["_additional"]

            documents_obj.append(
                {
                    "class": "No Class",
                    "uuid": _additional.get("id", "none"),
                    "chunks": document.get("chunk_count", 0),
                    "link": document.get("doc_link", ""),
                    "name": document.get("doc_name", "No name"),
                    "type": document.get("doc_type", "No type"),
                    "text": document.get("text", "No text"),
                    "timestamp": document.get("timestamp", ""),
                }
            )

        elapsed_time = round(time.time() - start_time, 2)  # Calculate elapsed time
        msg.good(
            f"Succesfully retrieved document: {len(documents)} documents in {elapsed_time}s"
        )

        doc_types = manager.retrieve_all_document_types()

        return JSONResponse(
            content={
                "documents": documents_obj,
                "doc_types": list(doc_types),
                "current_embedder": manager.embedder_manager.selected_embedder,
                "error": "",
                "took": elapsed_time,
            }
        )
    except Exception as e:
        msg.fail(f"All Document retrieval failed: {str(e)}")
        return JSONResponse(
            content={
                "documents": [],
                "doc_types": [],
                "current_embedder": manager.embedder_manager.selected_embedder,
                "error": f"All Document retrieval failed: {str(e)}",
                "took": 0,
            }
        )

# Delete specific document based on UUID
@app.post("/api/delete_document")
async def delete_document(payload: GetDocumentPayload):
    if production:
        msg.warn("Can't delete documents when in Production Mode")
        return JSONResponse(status_code=200, content={})

    msg.info(f"Document ID received: {payload.document_id}")

    manager.delete_document_by_id(payload.document_id)
    return JSONResponse(content={})

#for Ollama AGA
async def make_request(query_user):
    # Escape the query to handle special characters and newlines
    formatted_query = json.dumps(query_user)

    # Create a payload with the formatted query
    payload = QueryPayload(query=formatted_query)

    # Retrieve chunks and context
    chunks, context = manager.retrieve_chunks([payload.query])
    
    return context


async def grading_assistant(question_answer_pair, context):
    user_context = " ".join(context)
    print(context)
    rubric_content = f"""Please act as an impartial judge and evaluate the quality of the provided answer which attempts to answer the provided question based on a provided context.
            You'll be given context, question and answer to submit your reasoning and score for the correctness, comprehensiveness and readability of the answer. 
            Here is the context - {user_context}

            Below is your grading rubric: 
            - Correctness: If the answer correctly answers the question, below are the details for different scores:
            - Score 0: the answer is completely incorrect, doesn't mention anything about the question or is completely contrary to the correct answer.
                - For example, when asked “How to terminate a databricks cluster”, the answer is an empty string, or content that's completely irrelevant, or sorry I don't know the answer.
            - Score 1: the answer provides some relevance to the question and answers one aspect of the question correctly.
                - Example:
                    - Question: How to terminate a databricks cluster
                    - Answer: Databricks cluster is a cloud-based computing environment that allows users to process big data and run distributed data processing tasks efficiently.
                    - Or answer:  In the Databricks workspace, navigate to the "Clusters" tab. And then this is a hard question that I need to think more about it
            - Score 2: the answer mostly answers the question but is missing or hallucinating on one critical aspect.
                - Example:
                    - Question: How to terminate a databricks cluster”
                    - Answer: “In the Databricks workspace, navigate to the "Clusters" tab.
                    Find the cluster you want to terminate from the list of active clusters.
                    And then you'll find a button to terminate all clusters at once”
            - Score 3: the answer correctly answers the question and is not missing any major aspect. In this case, to score correctness 3, the final answer must be correct, final solution for numerical problems is of utmost importance.
                - Example:
                    - Question: How to terminate a databricks cluster
                    - Answer: In the Databricks workspace, navigate to the "Clusters" tab.
                    Find the cluster you want to terminate from the list of active clusters.
                    Click on the down-arrow next to the cluster name to open the cluster details.
                    Click on the "Terminate" button. A confirmation dialog will appear. Click "Terminate" again to confirm the action.”
            - Comprehensiveness: How comprehensive is the answer, does it fully answer all aspects of the question and provide comprehensive explanation and other necessary information. Below are the details for different scores:
            - Score 0: typically if the answer is completely incorrect, then the comprehensiveness is also zero.
            - Score 1: if the answer is correct but too short to fully answer the question, then we can give score 1 for comprehensiveness.
                - Example:
                    - Question: How to use databricks API to create a cluster?
                    - Answer: First, you will need a Databricks access token with the appropriate permissions. You can generate this token through the Databricks UI under the 'User Settings' option. And then (the rest is missing)
            - Score 2: the answer is correct and roughly answers the main aspects of the question, but it's missing description about details. Or is completely missing details about one minor aspect.
                - Example:
                    - Question: How to use databricks API to create a cluster?
                    - Answer: You will need a Databricks access token with the appropriate permissions. Then you'll need to set up the request URL, then you can make the HTTP Request. Then you can handle the request response.
                - Example:
                    - Question: How to use databricks API to create a cluster?
                    - Answer: You will need a Databricks access token with the appropriate permissions. Then you'll need to set up the request URL, then you can make the HTTP Request. Then you can handle the request response.
            - Score 3: the answer is correct, and covers all the main aspects of the question
            - Readability: How readable is the answer, does it have redundant information or incomplete information that hurts the readability of the answer.
            - Score 0: the answer is completely unreadable, e.g. full of symbols that's hard to read; e.g. keeps repeating the words that it's very hard to understand the meaning of the paragraph. No meaningful information can be extracted from the answer.
            - Score 1: the answer is slightly readable, there are irrelevant symbols or repeated words, but it can roughly form a meaningful sentence that covers some aspects of the answer.
                - Example:
                    - Question: How to use databricks API to create a cluster?
                    - Answer: You you  you  you  you  you  will need a Databricks access token with the appropriate permissions. And then then you'll need to set up the request URL, then you can make the HTTP Request. Then Then Then Then Then Then Then Then Then
            - Score 2: the answer is correct and mostly readable, but there is one obvious piece that's affecting the readability (mentioning of irrelevant pieces, repeated words)
                - Example:
                    - Question: How to terminate a databricks cluster
                    - Answer: In the Databricks workspace, navigate to the "Clusters" tab.
                    Find the cluster you want to terminate from the list of active clusters.
                    Click on the down-arrow next to the cluster name to open the cluster details.
                    Click on the "Terminate" button…………………………………..
                    A confirmation dialog will appear. Click "Terminate" again to confirm the action.
            - Score 3: the answer is correct and reader friendly, no obvious piece that affect readability.
            - Then final rating:
                - Ratio: 60'%' correctness + 20'%' comprehensiveness + 20'%' readability 
                - Example 1 of a final rating - 
                    Overall Score:
                        Correctness: 3
                        Comprehensiveness: 2
                        Readability: 2
                        Final Score = 60'%' of 3(correctness score) + 20'%' of 2(Comprehensiveness score) + 20'%' of 2(Readability score)
                                    = 1.8 + 0.4 + 0.4 = 2.6/3
                - Example 2 of a final rating -
                    Overall Score:
                        Correctness: 3
                        Comprehensiveness: 3
                        Readability: 3
                        Final Score = 60'%' of 3(correctness score) + 20'%' of 3(Comprehensiveness score) + 20'%' of 3(Readability score)
                                    = 1.8 + 0.6 + 0.6 = 3/3
            
            The format in which you should provide results-
                Correctness:
                    -Score(scale of 0 to 3)
                    -Explanation of score
                Readability:
                    -Score(scale of 0 to 3)
                    -Explanation of score
                Comprehensiveness:
                    -Score(scale of 0 to 3)
                    -Explanation of score
                
                Overall Score:
                    - Then final rating:
                        - Ratio: 60'%' correctness + 20'%' comprehensiveness + 20'%' readability 
                        Strictly follow this ratio of grading.
                            """
    payload = {
        "messages": [
            {"role": "system", "content": rubric_content},
            {"role": "user", "content": f"""Grade the following question-answer pair using the grading rubric and context provided - {question_answer_pair}"""}
        ],
        "stream": False,
        "options": {"top_k": 1, "top_p": 0, "temperature": 0, "seed": 100}
    }

    response = await asyncio.to_thread(ollama_chat, model='llama3', messages=payload['messages'], stream=payload['stream'])
    return response['message']['content']

@app.post("/api/ollamaAGA")
async def ollama_aqg(request: QueryRequest):
    query = request.query
    context = await make_request(query)
    if context is None:
        raise HTTPException(status_code=500, detail="Failed to fetch context")
    variants = await grading_assistant(query, context)
    return {"variants": variants}
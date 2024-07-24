from fastapi import FastAPI, WebSocket, File, UploadFile, status, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from ollama import chat as ollama_chat
from httpx import AsyncClient
import asyncio
import json
import httpx
import re , asyncio
import ollama
from pydantic import BaseModel
import base64
import logging 
from typing import List

import os
from pathlib import Path

from dotenv import load_dotenv
from starlette.websockets import WebSocketDisconnect
from wasabi import msg  # type: ignore[import]
import time
# from goldenverba.server.bitsp import(
#     ollama_afe,
#     ollama_aga,
#     ollama_aqg
# )
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
    "http://localhost/moodle", 
    "http://localhost", 
    "https://taxila-spanda.wilp-connect.net",
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

    print(f"Received payload: {payload}")
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

#for bitspprojs
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
    rubric_content = f"""<s> [INST] Please act as an impartial judge and evaluate the quality of the provided answer which attempts to answer the provided question based on a provided context.
            You'll be given context, question and answer to submit your reasoning and score for the correctness, comprehensiveness and readability of the answer. 
            
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
            The format in which you should provide results-
                Correctness:
                    -Score
                    -Explanation of score
                Readability:
                    -Score
                    -Explanation of score
                Comprehensiveness:
                    -Score
                    -Explanation of score
                            """
    payload = {
        "messages": [
            {"role": "system", "content": rubric_content},
            {"role": "user", "content": f"""Grade the following question-answer pair using the grading rubric and context provided - {question_answer_pair}"""}
        ],
        "stream": False,
        "options": {"top_k": 1, "top_p": 1, "temperature": 0, "seed": 100}
    }

    response = await asyncio.to_thread(ollama_chat, model='llama3.1', messages=payload['messages'], stream=payload['stream'])
    
    # Define a dictionary to store extracted scores
    scores_dict = {}

    # Extract the response content
    response_content = response['message']['content']

    # Define the criteria
    criteria = ["Correctness", "Readability", "Comprehensiveness"]

    # List to store individual scores
    scores = []

    for criterion in criteria:
        # Use regular expression to search for the criterion followed by 'Score:'
        criterion_pattern = re.compile(rf'{criterion}:\s*\**\s*Score\s*(\d+)', re.IGNORECASE)
        match = criterion_pattern.search(response_content)
        if match:
            # Extract the score value
            score_value = int(match.group(1).strip())
            scores.append(score_value)

    # Calculate the average score if we have scores
    avg_score = sum(scores) / len(scores) if scores else 0
    print(response['message']['content'])
    return response['message']['content'], avg_score


async def instructor_eval(instructor_name, context, score_criterion, explanation):
    # Define the criterion to evaluate
    user_context = "".join(context)
    # print(user_context)
    # Initialize empty dictionaries to store relevant responses and scores
    responses = {}
    scores_dict = {}
    # Initialize score_value with a default value
    score_value = None
    # Evaluation prompt template
    evaluate_instructions = f"""
        [INST]
        -Instructions:
            You are tasked with evaluating a teacher's performance based on the criterion: {score_criterion} - {explanation}.

        -Evaluation Details:
            -Focus exclusively on the provided video transcript.
            -Ignore interruptions from student entries/exits and notifications of participants 'joining' or 'leaving' the meeting.
            -Assign scores from 1 to 5:
        -Criteria:
            -Criterion Explanation: {explanation}
            -If the transcript lacks sufficient information to judge {score_criterion}, mark it as N/A and provide a clear explanation.
            -Justify any score that is not a perfect 5.
            -Consider the context surrounding the example statements, as the context in which a statement is made is extremely important.

            Rate strictly on a scale of 1 to 5 using whole numbers only.

            Ensure the examples are directly relevant to the evaluation criterion and discard any irrelevant excerpts.
        [/INST]
    """

    output_format = f"""Strictly follow the output format-
        -Output Format:
            -{score_criterion}: Score(range of 1 to 5, or N/A) - note: Do not use bold or italics or any formatting in this line.

            -Detailed Explanation with Examples and justification for examples:
                -Example 1: "[Quoted text from transcript]" [Description] [Timestamp]
                -Example 2: "[Quoted text from transcript]" [Description] [Timestamp]
                -Example 3: "[Quoted text from transcript]" [Description] [Timestamp]
                -...
                -Example n: "[Quoted text from transcript]" [Description] [Timestamp]
            -Include both positive and negative instances.
            -Highlight poor examples if the score is not ideal."""
    
    system_message = """This is a chat between a user and a judge. The judge gives helpful, detailed, and polite suggestions for improvement for a particular teacher from the given context - the context contains transcripts of videos. The assistant should also indicate when the judgement be found in the context."""
    
    formatted_transcripts = f"""Here are given transcripts for {instructor_name}-   
                    [TRANSCRIPT START]
                    {user_context}
                    [TRANSCRIPT END]"""
    
    user_prompt = f"""Please provide an evaluation of the teacher named '{instructor_name}' on the following criteria: '{score_criterion}'. Only include information from transcripts where '{instructor_name}' is the instructor."""

    # Define the payload
    payload = {
        "messages": [
            {
                "role": "system",
                "content": system_message
            },
            {
                "role": "user",
                "content": formatted_transcripts + "/n/n" + evaluate_instructions + "/n/n" + user_prompt + "/n/n" + output_format
            }
        ],
        "stream": False,
        "options": {
            "top_k": 1, 
            "top_p": 1, 
            "temperature": 0, 
            "seed": 100, 
            # "num_ctx": 10000
            # "num_predict": 100,  # Reduced for shorter outputs
            # "repeat_penalty": 1.2,  # Adjusted to reduce repetition
            # "presence_penalty": 1.5, # Adjusted to discourage repeated concepts
            # "frequency_penalty": 1.0 # Adjusted to reduce frequency of repeated tokens
        }
    }

    # Asynchronous call to the LLM API
    response = await asyncio.to_thread(ollama.chat, model='llama3.1', messages=payload['messages'], stream=payload['stream'])

    # Store the response
    responses[score_criterion] = response

    # Extract the score from the response content
    content = response['message']['content']

    # Adjust the regular expression to handle various cases including 'Score:', direct number, asterisks, and new lines
    pattern = rf'(?i)(score:\s*(\d+)|\**{re.escape(score_criterion)}\**\s*[:\-]?\s*(\d+))'

    match = re.search(pattern, content, re.IGNORECASE)

    if match:
        # Check which group matched and extract the score
        if match.group(2):  # This means 'Score:' pattern matched
            score_value = match.group(2).strip()  # group(2) contains the number after 'Score:'
        elif match.group(3):  # This means direct number pattern matched
            score_value = match.group(3).strip()  # group(3) contains the number directly after score criterion
        else:
            score_value = "N/A"  # Fallback in case groups are not as expected
        scores_dict[score_criterion] = score_value
    else:
        scores_dict[score_criterion] = "N/A"
        
    # If the score is still "N/A", check explicitly for the `**` case
    if score_value == "N/A":
        pattern_strict = rf'\*\*{re.escape(score_criterion)}\*\*\s*[:\-]?\s*(\d+)'
        match_strict = re.search(pattern_strict, content)
        if match_strict:
            score_value = match_strict.group(1).strip()
        else:
            score_value = "N/A"

    # Return the responses dictionary and scores dictionary
    return responses, scores_dict

# Function to generate answer using the Ollama API
async def answer_gen(question, context):
    user_context = "".join(context)
    # One shot example given in answer_inst should be the original question + original answer.
    answer_inst = f"""
        [INST]
        You are a highly knowledgeable and detailed assistant. Please follow these guidelines when generating answers:
        
        1. **Format**: Ensure the answer is nicely formatted and visually appealing. Use bullet points, numbered lists, headings, and subheadings where appropriate.
        
        2. **Clarity**: Provide clear and concise explanations. Avoid jargon unless it is necessary and explain it when used.
        
        3. **Math Questions**: 
        - Include all steps in the solution process.
        - Use clear and logical progression from one step to the next.
        - Explain each step briefly to ensure understanding.
        - Use LaTeX formatting for mathematical expressions to ensure they are easy to read and understand.

        4. **Non-Math Questions**:
        - Provide detailed explanations and context.
        - Break down complex ideas into simpler parts.
        - Use examples where appropriate to illustrate points.
        - Ensure the answer is comprehensive and addresses all parts of the question.
        
        5. **Tone**: Maintain a professional and friendly tone. Aim to be helpful and approachable.
        
        Here are a couple of examples to illustrate the format:
        ONE-SHOT-EXAMPLE-GOES-HERE
        [/INST]
    """
    user_prompt = f"""Based on the context : {user_context}, 
    
                    Please answer the following question - {question}"""

    payload = {
        "messages": [
            {
                "role": "system",
                "content": answer_inst
            },
            {
                "role": "user",
                "content": f"""Query: {user_prompt}"""
            }
        ],
        "stream": False,
        "options": {
            "top_k": 1,
            "top_p": 1,
            "temperature": 0,
            "seed": 100
        }
    }

    # Call ollama_chat function in a separate thread
    response = await asyncio.to_thread(ollama.chat, model='llama3.1', messages=payload['messages'], stream=payload['stream'])
    answer = response['message']['content']   

    return answer

# Define the endpoint
@app.post("/api/answergen")
async def answergen_ollama(request: QueryRequest):
    query = request.query
    context = await make_request(query)
    if context is None:
        raise HTTPException(status_code=500, detail="Failed to fetch context")
    
    answer = await answer_gen(query, context)
    response = {
        "answer": answer
    }
    return response


async def generate_question_variants(base_question, context):
    # Join the context into a single string
    user_context = " ".join(context)

    base_question_gen = f"""
    <s>Use the following context to guide your creation:
    [CONTEXT START]
    {context}
    [CONTEXT END]

    [INST] You are a creative problem designer specializing in creating diverse variants of educational problems. Your objective is to produce unique versions of a given problem by altering numerical parameters, contexts, and wording to prevent straightforward answer sharing. 
    Each variant should be based on the same core concept but presented in a way that makes each problem distinct and challenging - numerical values change for each variant.
    Focus on maintaining the educational intent while providing varied contexts and scenarios. Make sure each problem is self-contained and does not rely on the original problem statement. 
    
    Here are a few examples to illustrate the process:

    Example 1:
    Original Question: Analyze the impact of climate change on coastal cities.

    Generated Question Variants:
    1. Discuss how rising sea levels due to climate change affect coastal urban infrastructure.
    2. Evaluate the economic implications of climate change-induced flooding in coastal areas.
    3. How does climate change influence the frequency and intensity of storms in coastal regions?
    4. Assess the challenges faced by coastal communities in adapting to climate change.
    5. What measures can coastal cities implement to mitigate the effects of climate change?

    Example 2:
    Original Question: Calculate the molarity of a solution with 5 moles of solute in 2 liters of solution.

    Generated Question Variants:
    1. Determine the molarity of a solution containing 4 moles of solute in 1.5 liters of solution.
    2. Find the molarity of a solution with 7 moles of solute in 3 liters of solution.
    3. What is the molarity of a solution with 2.5 moles of solute in 1 liter of solution?
    4. Calculate the molarity of a solution containing 6 moles of solute in 2.5 liters of solution.
    5. If a solution has 8 moles of solute in 4 liters, what is its molarity?

    Example 3:
    Original Question: Sequence the first 10 prime numbers.

    Generated Question Variants:
    1. List the first 6 Fibonacci numbers in order.
    2. Identify the first 8 even numbers in sequence.
    3. What are the first 11 square numbers?
    4. Provide the first 12 terms of the geometric sequence starting with 1 and ratio 2.
    5. Sequence the first 9 odd numbers.

    Example 4:
    Original Question: If a score of 5 is multiplied by 0.2, which product is most popular based on these ratings: A, B, A, C, B, A, C, B, A, B?

    Generated Question Variants:
    1. With an initial score of 3 and a multiplier of 0.1, which app has the highest rating based on these reviews: X, Y, Z, X, X, Y, Z, X, Y, Z?
    2. Given a starting score of 4 and a multiplier of 0.15, identify the most popular book from this series of mentions: Book1, Book2, Book1, Book3, Book2, Book1, Book3, Book2, Book1, Book3?
    3. Using an initial score of 2 and a multiplier of 0.05, determine the top-rated movie from these ratings: MovieA, MovieB, MovieA, MovieC, MovieB, MovieA, MovieC, MovieB, MovieA, MovieB?
    4. With an initial score of 6 and a multiplier of 0.25, which song is most popular based on these plays: SongX, SongY, SongX, SongZ, SongY, SongX, SongZ, SongY, SongX, SongZ?
    5. Given a score of 4.5 and a multiplier of 0.3, find the most watched TV show from these episodes: Show1, Show2, Show1, Show3, Show2, Show1, Show3, Show2, Show1, Show3?

    Example 5:
    Original Question:
    A company uses a network of vending machines to send offers to nearby customers. If a machine is out of stock, it refers customers to the next nearest machine. [4]
    a) What happens if the connection between the data collection and analysis tiers is interrupted? How can this be mitigated? [2]
    b) Is storing historical data necessary? Why? [1]
    c) What message delivery semantics does this system require? [1]

    Generated Question Variants:
    1. Imagine a network of smart refrigerators that send promotional notifications to nearby shoppers. If a refrigerator is empty, it directs customers to the next nearest one. [4]
    a. What are the consequences of a prolonged interruption between the data collection and analysis systems? How can it be addressed? [2]
    b. Do you need to store historical data in this scenario? Why? [1]
    c. What kind of message delivery semantics is essential for this system? [1]
    2. Envision a system of intelligent parking meters that notify drivers of available spots and provide promotions. If a meter is occupied, it guides drivers to the nearest open spot. [4]
    a. What issues arise if the connection between data collection and analysis is severed? How can it be resolved? [2]
    b. Is it important to store historical data in this context? Why or why not? [1]
    c. What message delivery semantics should this system use? [1]
    3. Consider a network of smart grocery carts that inform customers of deals and promotions. If a cart is in use, it suggests the next available one. [4]
    a. What problems occur if the link between data collection and analysis breaks? How can they be mitigated? [2]
    b. Would it be necessary to store historical data in this situation? Why? [1]
    c. What message delivery semantics are required for this system? [1]
    [/INST]

    """


    # Define the payload for Ollama
    payload = {
        "messages": [
            {
                "role": "system",
                "content": base_question_gen
            },
            {
                "role": "user",
                "content": f"""
                Query - {base_question}

                Instructions:
                Alo NOTE that no two variants must be dependent on each other, each and every variant needs to be a standalone question which can be answered just by looking at the particular variant, and no external data. 
                Strictly follow the format for your responses:
                    generated_question_variants:
                    1.
                    2.
                    3.
                    ..
                    ..
                    n.
                    """,
            }
        ],
        "stream": False,
        "options": {
            "top_k": 1, 
            "top_p": 1, 
            "temperature": 0, 
            "seed": 100, 
        }
    }

    # Asynchronous call to Ollama API
    response = await asyncio.to_thread(ollama_chat, model='llama3.1', messages=payload['messages'], stream=payload['stream'])
    print(response['message']['content'])
    content = response['message']['content']    

    variants_dict = extract_variants(base_question, content)
    # print(variants_dict)
    # Return the response content
    return response['message']['content'], variants_dict

def extract_variants(base_question, content):
    # Regular expression to capture numbered or symbol-led variants
    pattern = r"^\s*(?:\d+[:.)\s-]+)(.*)$"
    
    # Find all matches using the pattern
    matches = re.findall(pattern, content, re.MULTILINE)
    
    # Extract the variants from the matches
    variants = [match.strip() for match in matches if match.strip()]
    
    # Return the dictionary with base question as key and variants as values
    return {base_question: variants}

@app.post("/api/ollamaAGA")
async def ollama_aga(request: QueryRequest):
    query = request.query
    context = await make_request(query)
    if context is None:
        raise HTTPException(status_code=500, detail="Failed to fetch context")
    variants, avg_score = await grading_assistant(query, context)
    print(avg_score)
    response = {
        "justification": variants,
        "average_score": avg_score
    }
    return response

@app.post("/api/ollamaAQG")
async def ollama_aqg(request: QueryRequest):
    query = request.query
    context = await make_request(query)
    variants, variants_dict = await generate_question_variants(query, context)
    response = {
        "variants": variants,
        "variants_dict": variants_dict
    }
    return response


@app.post("/api/ollamaAFE")
async def ollama_afe(request: QueryRequest):
    dimensions = {
        "Knowledge of Content and Pedagogy": "Understanding the subject matter and employing effective teaching methods.\n"
                                            "1: The transcript demonstrates minimal knowledge of content and ineffective pedagogical practices.\n"
                                            "2: The transcript demonstrates basic content knowledge but lacks pedagogical skills.\n"
                                            "3: The transcript demonstrates adequate content knowledge and uses some effective pedagogical practices.\n"
                                            "4: The transcript demonstrates strong content knowledge and consistently uses effective pedagogical practices.\n"
                                            "5: The transcript demonstrates exceptional content knowledge and masterfully employs a wide range of pedagogical practices.",

        "Breadth of Coverage": "Extent to which the instructor covers the required curriculum.\n"
                            "1: The transcript shows that the instructor covers minimal content with significant gaps in the curriculum.\n"
                            "2: The transcript shows that the instructor covers some content but with notable gaps in the curriculum.\n"
                            "3: The transcript shows that the instructor covers most of the required content with minor gaps.\n"
                            "4: The transcript shows that the instructor covers all required content thoroughly.\n"
                            "5: The transcript shows that the instructor covers all required content and provides additional enrichment material.",

        "Knowledge of Resources": "Awareness and incorporation of teaching resources.\n"
                                "1: The transcript shows that the instructor demonstrates minimal awareness of resources available for teaching.\n"
                                "2: The transcript shows that the instructor demonstrates limited knowledge of resources and rarely incorporates them.\n"
                                "3: The transcript shows that the instructor demonstrates adequate knowledge of resources and sometimes incorporates them.\n"
                                "4: The transcript shows that the instructor demonstrates strong knowledge of resources and frequently incorporates them.\n"
                                "5: The transcript shows that the instructor demonstrates extensive knowledge of resources and consistently incorporates a wide variety of them.",

        "Content Clarity": "Ability to explain complex concepts clearly and effectively.\n"
                        "1: Does not break down complex concepts, uses confusing, imprecise, and inappropriate language, and does not employ any relevant techniques or integrate them into the lesson flow.\n"
                        "2: Inconsistently breaks down complex concepts using language that is sometimes confusing or inappropriate, employing few minimally relevant techniques that contribute little to student understanding, struggling to integrate them into the lesson flow.\n"
                        "3: Generally breaks down complex concepts using simple, precise language and some techniques that are somewhat relevant and contribute to student understanding, integrating them into the lesson flow with occasional inconsistencies.\n"
                        "4: Frequently breaks down complex concepts using simple, precise language and a variety of relevant, engaging techniques that contribute to student understanding.\n"
                        "5: Consistently breaks down complex concepts using simple, precise language and a wide variety of highly relevant, engaging techniques such as analogies, examples, visuals, etc., seamlessly integrating them into the lesson flow.",

        "Differentiation Strategies": "Using strategies to meet diverse student needs.\n"
                                    "1: Uses no differentiation strategies to meet diverse student needs.\n"
                                    "2: Uses minimal differentiation strategies with limited effectiveness.\n"
                                    "3: Uses some differentiation strategies with moderate effectiveness.\n"
                                    "4: Consistently uses a variety of differentiation strategies effectively.\n"
                                    "5: Masterfully employs a wide range of differentiation strategies to meet the needs of all learners.",

        "Communication Clarity": "The ability to convey information and instructions clearly and effectively so that students can easily understand the material being taught.\n"
                                "1: Communicates poorly with students, leading to confusion and misunderstandings.\n"
                                "2: Communicates with some clarity but often lacks precision or coherence.\n"
                                "3: Communicates clearly most of the time, with occasional lapses in clarity.\n"
                                "4: Consistently communicates clearly and effectively with students.\n"
                                "5: Communicates with exceptional clarity, precision, and coherence, ensuring full understanding.",

        "Punctuality": "Consistently starting and ending classes on time.\n"
                    "1: Transcripts consistently show late class start times and/or early end times.\n"
                    "2: Transcripts occasionally show late class start times and/or early end times.\n"
                    "3: Transcripts usually show on-time class start and end times.\n"
                    "4: Transcripts consistently show on-time class start and end times.\n"
                    "5: Transcripts always show early class start times and full preparation to begin class on time.",

        "Managing Classroom Routines": "Implementing strategies to maintain order, minimize disruptions, and ensure a productive and respectful classroom environment.\n"
                                    "1: Classroom routines are poorly managed, leading to confusion and lost instructional time.\n"
                                    "2: Classroom routines are somewhat managed but with frequent disruptions.\n"
                                    "3: Classroom routines are adequately managed with occasional disruptions.\n"
                                    "4: Classroom routines are well-managed, leading to smooth transitions and minimal disruptions.\n"
                                    "5: Classroom routines are expertly managed, maximizing instructional time and creating a seamless learning environment.",

        "Managing Student Behavior": "Managing student behavior effectively to promote a positive and productive learning environment.\n"
                                    "1: Struggles to manage student behavior, leading to frequent disruptions and an unproductive learning environment. Rarely encourages student participation, with little to no effort to ensure equal opportunities for engagement; provides no or inappropriate feedback and compliments that do not support learning or motivation.\n"
                                    "2: Manages student behavior with limited effectiveness, with some disruptions and off-task behavior. Inconsistently encourages student participation, with unequal opportunities for engagement; provides limited or generic feedback and compliments that minimally support learning and motivation.\n"
                                    "3: Manages student behavior adequately, maintaining a generally productive learning environment. Generally encourages student participation and provides opportunities for engagement, but some students may dominate or be overlooked; provides feedback and compliments, but they may not always be specific or constructive.\n"
                                    "4: Effectively manages student behavior, promoting a positive and productive learning environment. Frequently encourages student participation, provides fair opportunities for engagement, and offers appropriate feedback and compliments that support learning and motivation.\n"
                                    "5: Expertly manages student behavior, fostering a highly respectful, engaged, and self-regulated learning community. Consistently encourages active participation from all students, ensures equal opportunities for engagement, and provides specific, timely, and constructive feedback and compliments that enhance learning and motivation.",

        "Adherence to Rules": "Consistently following and enforcing classroom and school policies, ensuring that both the teacher and students abide by established guidelines.\n"
                            "1: Consistently disregards or violates school rules and policies.\n"
                            "2: Occasionally disregards or violates school rules and policies.\n"
                            "3: Generally adheres to school rules and policies with occasional lapses.\n"
                            "4: Consistently adheres to school rules and policies.\n"
                            "5: Strictly adheres to school rules and policies and actively promotes compliance among students.",

        "Organization": "Organizing and presenting content in a structured and logical manner.\n"
                        "1: Transcripts indicate content that is poorly organized, with minimal structure and no clear emphasis on important content. Linking between content is absent or confusing.\n"
                        "2: Transcripts indicate content that is somewhat organized but lacks a consistent structure and comprehensive coverage. Emphasis on important content is inconsistent, and linking between content is weak.\n"
                        "3: Transcripts indicate content that is adequately organized, with a generally clear structure and comprehensive coverage. Important content is usually emphasized, and linking between content is present.\n"
                        "4: Transcripts indicate content that is well-organized, with a consistent and clear structure and comprehensive coverage. Important content is consistently emphasized, and linking between content is effective.\n"
                        "5: Transcripts indicate content that is exceptionally well-organized, with a highly structured, logical, and comprehensive presentation. Important content is strategically emphasized, and linking between content is seamless and enhances learning.",

        "Clarity of Instructional Objectives": "Presenting content clearly and effectively to facilitate understanding and mastery.\n"
                                            "1: Content is presented in a confusing or unclear manner.\n"
                                            "2: Content is presented with some clarity but with frequent gaps or inconsistencies.\n"
                                            "3: Content is presented with adequate clarity, allowing for general understanding.\n"
                                            "4: Content is presented with consistent clarity, promoting deep understanding.\n"
                                            "5: Content is presented with exceptional clarity, facilitating mastery and transfer of knowledge.",

        "Alignment with the Curriculum": "Ensuring instruction aligns with curriculum standards and covers required content.\n"
                                        "1: Instruction is poorly aligned with the curriculum, with significant gaps or deviations.\n"
                                        "2: Instruction is somewhat aligned with the curriculum but with frequent inconsistencies.\n"
                                        "3: Instruction is generally aligned with the curriculum, covering most required content.\n"
                                        "4: Instruction is consistently aligned with the curriculum, covering all required content.\n"
                                        "5: Instruction is perfectly aligned with the curriculum, covering all required content and providing meaningful extensions.",

        "Instructor Enthusiasm And Positive Demeanor": "Exhibiting a positive attitude and enthusiasm for teaching, inspiring student engagement.\n"
                                                    "1: Instructor exhibits a negative or indifferent demeanor and lacks enthusiasm for teaching.\n"
                                                    "2: Instructor exhibits a neutral demeanor and occasional enthusiasm for teaching.\n"
                                                    "3: Instructor exhibits a generally positive demeanor and moderate enthusiasm for teaching.\n"
                                                    "4: Instructor exhibits a consistently positive demeanor and strong enthusiasm for teaching.\n"
                                                    "5: Instructor exhibits an exceptionally positive demeanor and infectious enthusiasm for teaching, greatly inspiring student engagement.",

        "Awareness and Responsiveness to Student Needs": "Demonstrating attentiveness and responding appropriately to student needs and feedback.\n"
                                                        "1: Lacks awareness of or fails to respond to student needs and feedback.\n"
                                                        "2: Occasionally demonstrates awareness of and responds to student needs and feedback.\n"
                                                        "3: Generally demonstrates awareness of and responds to student needs and feedback.\n"
                                                        "4: Consistently demonstrates awareness of and responds to student needs and feedback.\n"
                                                        "5: Highly attuned to and proactively responds to student needs and feedback, fostering a supportive learning environment."
    }


    instructor_name = request.query

    all_responses = {}
    all_scores = {}

    for dimension, explanation in dimensions.items():
        query = f"Judge {instructor_name} based on {dimension}."
        context = await make_request(query)  # Assuming make_request is defined elsewhere to get the context
        # print(f"CONTEXT for {dimension}:")
        # print(context)  # Print the context generated
        result_responses, result_scores = await instructor_eval(instructor_name, context, dimension, explanation)
        print(result_responses)
        print(result_scores)
        # Extract only the message['content'] part and store it
        all_responses[dimension] = result_responses[dimension]['message']['content']
        all_scores[dimension] = result_scores[dimension]
    
    print("SCORES:")
    print(json.dumps(all_scores, indent=2))
    response = {
        "DOCUMENT": all_responses,
        "SCORES": all_scores
    }
    
    return response












# Modified import endpoint to handle transcript uploads
@app.post("/api/importTranscript")
async def import_transcript(transcript_data: UploadFile = File(...)):
    try:
        contents = await transcript_data.file.read()

        # Convert to Base64
        base64_content = base64.b64encode(contents).decode('utf-8')

        # Upload to Weaviate using the existing endpoint
        upload_to_weaviate(base64_content, transcript_data.filename)

        return JSONResponse(content={"message": "Transcript uploaded successfully"})
    except ValidationError as e:
        # Handle validation errors
        return JSONResponse(content={"error": e.errors()}, status_code=422)
    except HTTPException as e:
        raise e  # Reraise the exception if it's a Weaviate import failure
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

class FileData(BaseModel):
    filename: str
    extension: str
    content: str

class ImportPayload(BaseModel):
    data: list[FileData]
    textValues: list
    config: dict

class QueryRequest(BaseModel):
    query: str

@app.post("/api/upload_transcript")
async def upload_transcript(payload: ImportPayload):
    try:
        for file_data in payload.data:
            file_content = base64.b64decode(file_data.content)
            with open(file_data.filename, "wb") as file:
                file.write(file_content)
        
        logging = []

        print(f"Received payload: {payload}")
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


    except Exception as e:
        print(f"Error during import: {e}")
        raise HTTPException(status_code=500, detail="Error processing the file")
    
@app.post("/api/evaluate_Transcipt")
async def evaluate_Transcipt(request: QueryRequest):
    dimensions = {
        "Communication Clarity": "The ability to convey information and instructions clearly and effectively so that students can easily understand the material being taught.\n"
                                "0: Instructions are often vague or confusing, leading to frequent misunderstandings among students.\n"
                                "Example: 'Read the text and do the thing.'\n"
                                "1: Occasionally provides clear instructions but often lacks detail, requiring students to ask for further clarification.\n"
                                "Example: 'Read the chapter and summarize it.'\n"
                                "2: Generally clear and detailed in communication, though sometimes slightly ambiguous.\n"
                                "Example: 'Read chapter 3 and summarize the main points in 200 words.'\n"
                                "3: Always communicates instructions and information clearly, precisely, and comprehensively, ensuring students fully understand what is expected.\n"
                                "Example: 'Read chapter 3, identify the main points, and write a 200-word summary. Make sure to include at least three key arguments presented by the author.'",

        "Punctuality": "Consistently starting and ending classes on time, as well as meeting deadlines for assignments and other class-related activities.\n"
                    "0: Frequently starts and ends classes late, often misses deadlines for assignments and class-related activities.\n"
                    "Example: Class is supposed to start at 9:00 AM but often begins at 9:15 AM, and assignments are returned late.\n"
                    "1: Occasionally late to start or end classes and sometimes misses deadlines.\n"
                    "Example: Class sometimes starts a few minutes late, and assignments are occasionally returned a day late.\n"
                    "2: Generally punctual with minor exceptions, mostly meets deadlines.\n"
                    "Example: Class starts on time 90%' of the time, and assignments are returned on the due date.\n"
                    "3: Always starts and ends classes on time, consistently meets deadlines for assignments and other activities.\n"
                    "Example: Class starts exactly at 9:00 AM every day, and assignments are always returned on the specified due date.",

        "Positivity": "Maintaining a positive attitude, providing encouragement, and fostering a supportive and optimistic learning environment.\n"
                    "0: Rarely displays a positive attitude, often appears disengaged or discouraging.\n"
                    "Example: Rarely smiles or offers encouragement, responds negatively to student questions.\n"
                    "1: Occasionally positive, but can be inconsistent in attitude and support.\n"
                    "Example: Sometimes offers praise but often seems indifferent.\n"
                    "2: Generally maintains a positive attitude and provides encouragement, though with occasional lapses.\n"
                    "Example: Usually offers praise and support but has off days.\n"
                    "3: Consistently maintains a positive and encouraging attitude, always fostering a supportive and optimistic environment.\n"
                    "Example: Always greets students warmly, frequently provides positive feedback and encouragement.",

    }


    instructor_name = request.query

    all_responses = {}
    all_scores = {}

    for dimension, explanation in dimensions.items():
        query = f"Judge document name {instructor_name} based on {dimension}."
        context = await make_request(query)  # Assuming make_request is defined elsewhere to get the context
        # print(f"CONTEXT for {dimension}:")
        # print(context)  # Print the context generated
        result_responses, result_scores = await instructor_eval(instructor_name, context, dimension, explanation)
        print(result_responses)
        print(result_scores)
        # Extract only the message['content'] part and store it
        all_responses[dimension] = result_responses[dimension]['message']['content']
        all_scores[dimension] = result_scores[dimension]
    
    print("SCORES:")
    print(json.dumps(all_scores, indent=2))
    response = {
        "DOCUMENT": all_responses,
        "SCORES": all_scores
    }
    
    return response

async def resume_eval(resume_name, jd_name, context, score_criterion, explanation):
    user_context = "".join(context)
    responses = {}
    scores_dict = {}

    evaluate_instructions = f"""
        [INST]
        -Instructions:
            You are tasked with evaluating a resume named {resume_name} in comparison to a job description named {jd_name} based on the criterion: {score_criterion} - {explanation}.

        -Evaluation Details:
            -Focus exclusively on the provided resume and job description.
            -Assign scores from 0 to 3:
                0: Poor performance
                1: Average performance
                2: Good performance
                3: Exceptional performance
        -Criteria:
            -Criterion Explanation: {explanation}
            -If the resume and job description lack sufficient information to judge {score_criterion}, mark it as N/A and provide a clear explanation.
            -Justify any score that is not a perfect 3.

        Strictly follow the output format-
        -Output Format:
            -{score_criterion}: Score: score(range of 0 to 3, or N/A)

            -Detailed Explanation with Examples and justification for examples:
                -Example 1: "[Quoted text from resume/job description]" [Description]
                -Example 2: "[Quoted text from resume/job description]" [Description]
                -Example 3: "[Quoted text from resume/job description]" [Description]
                -...
                -Example n: "[Quoted text from resume/job description]" [Description]
            -Include both positive and negative instances.
            -Highlight poor examples if the score is not ideal.

            -Consider the context surrounding the example statements, as the context in which a statement is made is extremely important.

            Rate strictly on a scale of 0 to 3 using whole numbers only.

            Ensure the examples are directly relevant to the evaluation criterion and discard any irrelevant excerpts.
        [/INST]
    """
    system_message = """This is a chat between a user and a judge. The judge gives helpful, detailed, and polite suggestions for improvement for a candidate's resume based on the given context - the context contains resumes and job descriptions. The assistant should also indicate when the judgement be found in the context."""

    formatted_context = f"""Here are given documents:
                    [RESUME START]
                    {user_context}
                    [RESUME END]
                    [JOB DESCRIPTION START]
                    {user_context}
                    [JOB DESCRIPTION END]"""

    user_prompt = f"""Please provide an evaluation of the resume named '{resume_name}' in comparison to the job description named '{jd_name}' on the following criteria: '{score_criterion}'. Only include information from the provided documents."""

    payload = {
        "messages": [
            {
                "role": "system",
                "content": system_message
            },
            {
                "role": "user",
                "content": formatted_context + "/n/n" + evaluate_instructions + "/n/n" + user_prompt + " Strictly follow the format of output provided."
            }
        ],
        "stream": False,
        "options": {
            "top_k": 1,
            "top_p": 1,
            "temperature": 0,
            "seed": 100
        }
    }

    response = await asyncio.to_thread(ollama.chat, model='llama3.1', messages=payload['messages'], stream=payload['stream'])
    responses[score_criterion] = response
    content = response['message']['content']

    pattern = rf'(score:\s*([\s\S]*?)(\d+)|\**{score_criterion}\**\s*:\s*(\d+))'
    match = re.search(pattern, content, re.IGNORECASE)

    if match:
        if match.group(3):
            score_value = match.group(3).strip()
        elif match.group(4):
            score_value = match.group(4).strip()
        else:
            score_value = "N/A"
        scores_dict[score_criterion] = score_value
    else:
        scores_dict[score_criterion] = "N/A"

    return responses, scores_dict


# Define the extract_score function
def extract_score(response_content):
    # Regular expression to find the score in the response
    score_match = re.search(r'Score:\s*(\d+|N/A)', response_content)
    if score_match:
        score = score_match.group(1)
        if score == 'N/A':
            return score
        return int(score)
    return None

async def resume_eval(resume_name, jd_name, context, score_criterion, explanation):
    user_context = "".join(context)
    responses = {}
    scores_dict = {}

    evaluate_instructions = f"""
        [INST]
        -Instructions:
            You are tasked with evaluating a candidate's resume in comparison to a job description based on the criterion: {score_criterion} - {explanation}.

        -Evaluation Details:
            -Focus exclusively on the provided resume and job description.
            -Assign scores from 0 to 3:
                0: Poor performance
                1: Average performance
                2: Good performance
                3: Exceptional performance
        -Criteria:
            -Criterion Explanation: {explanation}
            -If the resume lacks sufficient information to judge {score_criterion}, mark it as N/A and provide a clear explanation.
            -Justify any score that is not a perfect 3.

        Strictly follow the output format-
        -Output Format:
            -{score_criterion}: Score: score(range of 0 to 3, or N/A)

            -Detailed Explanation with Examples and justification for examples:
                -Example 1: "[Quoted text from resume or job description]" [Description]
                -Example 2: "[Quoted text from resume or job description]" [Description]
                -Example 3: "[Quoted text from resume or job description]" [Description]
                -...
                -Example n: "[Quoted text from resume or job description]" [Description]
            -Include both positive and negative instances.
            -Highlight poor examples if the score is not ideal.

            -Consider the context surrounding the example statements, as the context in which a statement is made is extremely important.

            Rate strictly on a scale of 0 to 3 using whole numbers only.

            Ensure the examples are directly relevant to the evaluation criterion and discard any irrelevant excerpts.
        [/INST]
    """
    system_message = """This is a chat between a user and a judge. The judge gives helpful, detailed, and polite suggestions for improvement for a particular candidate from the given context - the context contains resumes and job descriptions. The assistant should also indicate when the judgment is found in the context."""
    
    formatted_documents = f"""Here are the given documents for {resume_name} and {jd_name}:
                    [RESUME START]
                    {user_context}
                    [RESUME END]
                    [JOB DESCRIPTION START]
                    {user_context}
                    [JOB DESCRIPTION END]"""
    
    user_prompt = f"""Please provide an evaluation of the candidate named '{resume_name}' in comparison to the job description named '{jd_name}' on the following criteria: '{score_criterion}'. Only include information from the resume and job description where '{resume_name}' is the candidate."""

    payload = {
        "messages": [
            {
                "role": "system",
                "content": system_message
            },
            {
                "role": "user",
                "content": formatted_documents + "\n\n" + evaluate_instructions + "\n\n" + user_prompt
            }
        ],
        "stream": False  # Assuming that streaming is set to False, adjust based on your implementation
    }

    eval_response = await asyncio.to_thread(ollama.chat, model='llama3.1', messages=payload['messages'])  # Assuming chat function is defined to handle the completion request

    # Log the eval_response to see its structure
    print("eval_response:", eval_response)
    
    try:
        eval_response_content = eval_response['message']['content']
    except KeyError as e:
        raise KeyError(f"Expected key 'message' not found in response: {eval_response}")

    response = {
        score_criterion: {
            "message": {
                "content": eval_response_content
            }
        }
    }
    score = extract_score(eval_response_content)
    scores_dict[score_criterion] = score

    return response, scores_dict



class QueryRequest(BaseModel):
    query: List[str]

@app.post("/api/evaluate_Resume")
async def evaluate_Resume(request: QueryRequest):
    if len(request.query) != 2:
        raise HTTPException(status_code=400, detail="Invalid request format. Expected two items in query list.")
    
    resume_name, jd_name = request.query
    dimensions = {
        "Qualification Match": "The extent to which the candidate's educational background, certifications, and experience align with the specific requirements outlined in the job description.\n"
            "0: Qualifications are largely unrelated to the position.\n"
            "Example: The job requires a Master's degree in Computer Science, but the candidate has a Bachelor's in History.\n"
            "1: Some relevant qualifications but significant gaps exist.\n"
            "Example: The candidate has a Bachelor's in Computer Science but lacks the required 3 years of industry experience.\n"
            "2: Mostly meets the qualifications with minor gaps.\n"
            "Example: The candidate meets most qualifications but lacks experience with a specific programming language mentioned in the job description.\n"
            "3: Exceeds qualifications, demonstrating additional relevant skills or experience.\n"
            "Example: The candidate exceeds the required experience and has additional certifications in relevant areas.",
        "Experience Relevance": "The degree to which the candidate's prior teaching, research, or industry experience is relevant to the courses they would be teaching.\n"
            "0: Little to no relevant experience in the subject matter.\n"
            "Example: The candidate has no prior experience teaching or working with the programming languages listed in the course syllabus.\n"
            "1: Some relevant experience but mostly in unrelated areas.\n"
            "Example: The candidate has experience in web development but the course focuses on mobile app development.\n"
            "2: Solid experience in related fields but limited direct experience in the specific subject.\n"
            "Example: The candidate has taught general computer science courses but not the specific advanced algorithms course they are applying for.\n"
            "3: Extensive experience directly teaching or working in the subject area.\n"
            "Example: The candidate has 5+ years of experience teaching the specific course they are applying for and has published research in the field.",
        "Skillset Alignment": "How well the candidate's demonstrated skills (e.g., technical skills, communication, leadership) match the required competencies for the role.\n"
            "0: Skills are largely misaligned with the job requirements.\n"
            "Example: The job requires strong communication and presentation skills, but the candidate has no experience presenting or leading workshops.\n"
            "1: Possesses some required skills but lacks others.\n"
            "Example: The candidate has strong technical skills but lacks experience with collaborative project management tools.\n"
            "2: Demonstrates most of the required skills with some room for improvement.\n"
            "Example: The candidate has good communication skills but could benefit from additional training in public speaking.\n"
            "3: Possesses all required skills and demonstrates advanced abilities in some areas.\n"
            "Example: The candidate has excellent technical skills, is a highly effective communicator, and has a proven track record of mentoring junior developers.",
        "Potential Impact": "An assessment of the candidate's potential to contribute positively to the department and the institution as a whole, based on their resume and cover letter.\n"
            "0: Unclear or negative potential impact based on application materials.\n"
            "Example: The candidate's application materials are vague and do not highlight any specific contributions they could make.\n"
            "1: Potential for minimal impact or contribution.\n"
            "Example: The candidate's resume shows basic qualifications but no indication of going above and beyond.\n"
            "2: Demonstrates potential for moderate positive impact.\n"
            "Example: The candidate has experience with relevant projects and expresses enthusiasm for contributing to the department's research initiatives.\n"
            "3: Shows strong potential to significantly impact the department and institution through teaching, research, or other activities.\n"
            "Example: The candidate has a strong publication record, outstanding references, and a clear vision for how they would enhance the curriculum.",
        "Overall Fit": "A holistic assessment of how well the candidate aligns with the department's culture, values, and long-term goals.\n"
            "0: Poor overall fit with the department.\n"
            "Example: The candidate's values and goals conflict with the department's focus on collaborative learning.\n"
            "1: Some alignment but significant differences in values or goals.\n"
            "Example: The candidate is passionate about research but the department prioritizes teaching excellence.\n"
            "2: Good fit with some areas of potential misalignment.\n"
            "Example: The candidate aligns well with most of the department's values but has a different teaching style than is typical for the institution.\n"
            "3: Excellent fit with the department's culture, values, and goals.\n"
            "Example: The candidate's teaching philosophy, research interests, and collaborative spirit perfectly complement the department's existing strengths and future aspirations."
    }

    all_responses = {}
    all_scores = {}

    for dimension, explanation in dimensions.items():
        query = f"Judge Resume named {resume_name} in comparison to Job Description named {jd_name} based on {dimension}."
        context = await make_request(query)  # Assuming make_request is defined elsewhere to get the context
        result_responses, result_scores = await resume_eval(resume_name, jd_name, context, dimension, explanation)
        all_responses[dimension] = result_responses[dimension]['message']['content']
        all_scores[dimension] = result_scores[dimension]
    
    response = {
        "DOCUMENT": all_responses,
        "SCORES": all_scores
    }
    
    return response


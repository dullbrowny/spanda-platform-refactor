import ollama
import httpx
import asyncio
import json 

async def make_request(query):
    async with httpx.AsyncClient(timeout=None) as client:  # Set timeout to None to wait indefinitely
        # Define the endpoint URL
        query_url = "http://localhost:8000/api/query"

        # Define the payload
        payload = {
            "query": query
        }

        try:
            # Make a POST request to the /api/query endpoint
            response_query = await client.post(query_url, json=payload)
            if response_query.status_code == 200:
                response_data = response_query.json()
                print("Successfully retrieved context!")
                return response_data.get("context", "No context provided")
            else:
                print(f"Query Request failed with status code {response_query.status_code}")
                return None
        except httpx.RequestError as exc:
            print(f"An error occurred while requesting {exc.request.url!r}: {exc}")
            return None

async def instructor_eval(instructor_name, context, score_criterion):
    # Define the criterion to evaluate
    user_context = " ".join(context)

    # Initialize empty dictionaries to store relevant responses and scores
    responses = {}
    scores_dict = {}

    # Evaluation prompt template
    evaluate_instructor = f"""
    You are Verba, The Golden RAGtriever, a chatbot for Retrieval Augmented Generation (RAG). You will receive a user query and context pieces that have a semantic similarity to that specific query. Please answer these user queries only with their provided context. If the provided documentation does not provide enough information, say so. If the user asks questions about you as a chatbot specifically, answer them naturally. If the answer requires code examples, encapsulate them with ```programming-language-name ```. Don't do pseudo-code.
    """

    # Define the payload
    payload = {
        "messages": [
            {
                "role": "system",
                "content": evaluate_instructor
            },
            {
                "role": "user",
                "content": f"""
                Here are your transcripts -
                [TRANSCRIPT START]
                    {context}
                [TRANSCRIPT END]

                <s> [INST] You are tasked with evaluating a teacher's performance based solely on {score_criterion}. Your assessment should be derived from a provided video transcript, ignoring any interruptions caused by student entries or exits and any notifications of participants 'joining the meeting' or 'leaving the meeting.' Assign scores from 0 to 5, where 0 indicates poor performance and 5 indicates exceptional performance. 
                If the transcript lacks sufficient information to judge {score_criterion}, mark it as N/A and provide a clear explanation. If the score is not a perfect score, justify why. 
                Please evaluate this instructor - {instructor_name}.

                Provide the evaluation strictly in the following format without any unnecessary words:

                {score_criterion} -
                Score: SCORE
                Detailed explanation of score with examples from the transcript:
                [Overall Summary]
                Example 1: ...
                Example 2: ...
                Example 3: ...
                ....
                Example n: ...

                These examples must contain good examples and bad examples. If the score is not ideal, showcase bad examples too.

                Rate on a scale of 0 to 5. Strictly follow this scale. Please use whole numbers.
                """
            }
        ],
        "stream": False,
        "options": {
            "top_k": 1, 
            "top_p": 1, 
            "temperature": 0.0, 
            "seed": 100, 
        }
    }

    # Asynchronous call to the LLM API
    response = await asyncio.to_thread(ollama.chat, model='llama3', messages=payload['messages'], stream=payload['stream'])

    # Store the response
    responses[score_criterion] = response

    # Extract the score from the response content
    content = response['message']['content']
    score_index = content.find("Score:")
    if score_index != -1:
        score_value = content[score_index + len("Score:"):].strip().split("\n")[0].strip()
        scores_dict[score_criterion] = score_value
    else:
        scores_dict[score_criterion] = "N/A"

    # Return the responses dictionary and scores dictionary
    return responses, scores_dict


# # Example usage
# async def main():
#     dimensions = [
#         "Communication Clarity",
#         "Punctuality",
#         "Positivity",
#         "Personal Engagement",
#         "Classroom Management Practices",
#         "Adherence to Rules",
#         "Classroom Atmosphere",
#         "Student Participation"
#     ]
#     instructor_name = "NANDAGOPAL GOVINDAN"
#     # instructor_name = "SANGVE SUNIL MAHADEV"
#     # instructor_name = "ASHUTOSH BHATIA"


#     all_responses = {}
#     all_scores = {}

#     for dimension in dimensions:
#         query = f"Based on the following criteria: {dimension}, Please evaluate the following teacher: {instructor_name}. Only evaluate the particular criteria based on the transcript, do not evaluate other criteria."
#         context = await make_request(query)  # Assuming make_request is defined elsewhere to get the context
#         print(f"CONTEXT for {dimension}:")
#         print(context)  # Print the context generated
#         result_responses, result_scores = await instructor_eval(instructor_name, context, dimension)
        
#         # Extract only the message['content'] part and store it
#         all_responses[dimension] = result_responses[dimension]['message']['content']
#         all_scores[dimension] = result_scores[dimension]

#     print("DOCUMENT:")
#     print(json.dumps(all_responses, indent=2))  # Convert to JSON string for pretty printing
#     print("SCORES:")
#     print(json.dumps(all_scores, indent=2))     # Convert to JSON string for pretty printing

# # Run the async main function
# asyncio.run(main())

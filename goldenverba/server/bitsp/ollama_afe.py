import ollama
import httpx
import asyncio

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

async def instructor_eval(instructor_name, context):
    # Define the scores to evaluate
    scores = [
        "Communication Clarity",
        "Positivity",
        "Personal Engagement",
        "Classroom Management Practices",
        "Adherence to Rules",
        "Classroom Atmosphere",
        "Student Participation"
    ]

    user_context = " ".join(context)

    # Initialize empty dictionaries to store relevant responses and scores
    responses = {}
    scores_dict = {}

    # Loop over each score element
    for score in scores:
        evaluate_instructor = f"""You are tasked with evaluating a teacher's performance based solely on {score}. Your assessment should be derived from a provided video transcript, ignoring any interruptions caused by student entries or exits and any notifications of participants 'joining the meeting' or 'leaving the meeting.' Assign scores from 0 to 3, where 0 indicates poor performance and 3 indicates exceptional performance. If the transcript lacks sufficient information to judge {score}, mark it as N/A and provide a clear explanation.
        Here are your transcripts - 
        [TRANSCRIPT START]
            {user_context}
        [TRANSCRIPT END]
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
                                Please evaluate this instructor - {instructor_name}.

                                Provide the evaluation strictly in the following format without any unnecessary words:

                                {score} - 
                                Score: SCORE
                                Detailed explanation of score with examples from the transcript:
                                Example 1: ...
                                Example 2: ...
                                Example 3: ...
                                ....
                                Example n: ...

                                Rate on a scale of 1 to 5. Strictly follow this scale. Please use whole numbers. Be generous when assigning scores.
                                """
                }
            ],
            "stream": False,
            "options": {
                "top_k": 1, 
                "top_p": 0, 
                "temperature": 0, 
                "seed": 100, 
            }
        }

        # Asynchronous call to the LLM API
        response = await asyncio.to_thread(ollama.chat, model='llama3', messages=payload['messages'], stream=payload['stream'])

        # Store the response
        responses[score] = response

    # Iterate through the responses and extract scores
    for score, response in responses.items():
        # Extract the score from the response content
        content = response['message']['content']
        score_index = content.find("Score:")
        if score_index != -1:
            score_value = content[score_index + len("Score:"):].strip().split("\n")[0].strip()
            scores_dict[score] = score_value
        else:
            scores_dict[score] = "N/A"

    # Return the responses dictionary and scores dictionary
    return responses, scores_dict




# # Example usage
# async def main():
#     query = "SANGVE SUNIL MAHADEV"
#     context = await make_request(query)
#     print("CONTEXT:")
#     print(context)  # Print the context generated
#     result_responses, result_scores = await instructor_eval(query, context)
#     print("DOCUMENT:")
#     print(result_responses)
#     print("SCORES:")
#     print(result_scores)

# # Run the async main function
# asyncio.run(main())

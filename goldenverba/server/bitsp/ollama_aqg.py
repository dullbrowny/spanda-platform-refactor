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

async def generate_question_variants(base_question, n, context):
    # Join the context into a single string
    user_context = " ".join(context)

    base_question_gen = f"""
    You are an inventive educator dedicated to nurturing critical thinking skills, your task is to devise a series of a number of distinct iterations of a mathematical problem or a textual problem. Each iteration should be rooted in a fundamental problem-solving technique, but feature diverse numerical parameters and creatively reworded text to discourage students from sharing answers. Your objective is to generate a collection of unique questions that not only promote critical thinking but also thwart easy duplication of solutions. Ensure that each variant presents different numerical values, yielding disparate outcomes. Each question should have its noun labels changed. Additionally, each question should stand alone without requiring reference to any other question, although they may share the same solving concept. Your ultimate aim is to fashion an innovative array of challenges that captivate students and inspire analytical engagement.
    Strictly use the following context to generate the questions, do not ask questions out of the scope of the following context - 
    Context: {user_context}

    Strictly follow the following format while providing variants of questions -
    generated_question_variants-
    (all variants generated with proper labelling)

    Examples(I will provide example input prompts and expected responses):
    *Example (Textual):*
    Please generate 3 variants of the question: What is the capital of France?
    generated_question_variants-
    1: In which European country is Paris located?
    2: What is the capital of Italy?
    3: What is the capital of Spain?
    - This is a based on Capitals of different countries from provided context.

    *Example (Textual):*
    Please generate 5 variants of the question: What is the turning test?
    generated_question_variants-
    1: How does the concept of the Turing Test contribute to our understanding of human-computer interaction in the realm of artificial intelligence?
    2: What implications do the results of the Turing Test have for the development of conversational AI systems?
    3: In what ways does the Turing Test influence the design and evaluation of chatbots and other interactive AI agents?
    4: How has the Turing Test shaped our notion of intelligence and its relationship to machine learning in the field of AI?
    5: What insights do the outcomes of the Turing Test offer into the potential applications and limitations of language-based AI systems?
    - These are questions based on the Turning test from provided context.

    *Example (Math):*
    Please generate 5 variants of the question: "What is the perimeter of a square if each side measures 5 centimeters?"
    generated_question_variants-
    1. "Find the total length of a rectangle's border if its width is 3 meters and its height is 4 meters."
    2. "Determine the circumference of a circle with a radius of 7 millimeters."
    3. "Calculate the boundary length of an equilateral triangle with each side measuring 8 inches."
    4. "What is the total distance around a polygon with four sides, where one side measures 9 feet and another side measures 12 feet?"
    5. "Discover the perimeter of a rhombus if its diagonal measures 15 centimeters."
    - These are practice problems for basic geometry.
    Explanation: The generated questions are similar to the originals but rephrased using different wording or focusing on a different aspect of the problem (area vs. perimeter, speed vs. time). These are from provided context.
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
                "content": f"Please generate {n} variants of the question: '{base_question}'",
            }
        ],
        "stream": False,
        "options": {
            "top_k": 20, 
            "top_p": 0.9, 
            "temperature": 0.7, 
            "repeat_penalty": 1.2, 
            "presence_penalty": 1.5, 
            "frequency_penalty": 1.0, 
            "mirostat": 1, 
            "mirostat_tau": 0.8, 
            "mirostat_eta": 0.6, 
        }
    }

    # Asynchronous call to Ollama API
    response = await asyncio.to_thread(ollama.chat, model='llama3', messages=payload['messages'], stream=payload['stream'])

    # Return the response content
    return response['message']['content']

# Example usage
async def main():
    query = "What is the area of a rectangle with length 10 units and width 5 units?"
    context = await make_request(query)
    n = 7
    variants = await generate_question_variants(query, n, context)
    print(variants)

# Run the async main function
asyncio.run(main())

import requests
from docx import Document
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import re

# Replace with your Moodle instance URL and token
MOODLE_URL = 'http://localhost/moodle/moodle-4.2.1'
TOKEN = '80a42dd70578d1274a40e6994eafbb63'
COURSE_ID = '2'  # Correct course ID

# Function to make a Moodle API call
def moodle_api_call(params):
    endpoint = f'{MOODLE_URL}/webservice/rest/server.php'
    response = requests.get(endpoint, params=params)
    print("Status Code:", response.status_code)

    try:
        result = response.json()
    except ValueError as e:
        raise ValueError(f"Error parsing JSON response: {response.text}") from e

    if 'exception' in result:
        raise Exception(f"Error: {result['exception']['message']}")

    return result

# Function to get enrolled users in a specific course
def get_enrolled_users():
    params = {
        'wstoken': TOKEN,
        'wsfunction': 'core_enrol_get_enrolled_users',
        'moodlewsrestformat': 'json',
        'courseid': COURSE_ID
    }
    return moodle_api_call(params)

# Function to get assignments for a specific course
def get_assignments():
    params = {
        'wstoken': TOKEN,
        'wsfunction': 'mod_assign_get_assignments',
        'moodlewsrestformat': 'json',
        'courseids[0]': COURSE_ID
    }
    assignments = moodle_api_call(params)
    
    if not assignments.get('courses'):
        raise Exception("No courses found.")
    
    return assignments['courses'][0]['assignments']

# Function to get submissions for a specific assignment
def get_submissions(assignment_id):
    params = {
        'wstoken': TOKEN,
        'wsfunction': 'mod_assign_get_submissions',
        'moodlewsrestformat': 'json',
        'assignmentids[0]': assignment_id
    }
    submissions = moodle_api_call(params)
    
    if not submissions.get('assignments'):
        return []

    return submissions['assignments'][0]['submissions']

# Function to download a file from a given URL
def download_file(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.content
    else:
        raise Exception(f"Failed to download file: {response.status_code}, URL: {url}")

# Function to extract text from a PDF file
def extract_text_from_pdf(file_content):
    doc = fitz.open(stream=file_content, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    return text

# Function to extract text from a DOCX file
def extract_text_from_docx(file_content):
    with io.BytesIO(file_content) as f:
        doc = Document(f)
        return "\n".join([para.text for para in doc.paragraphs])

# Function to extract text from a TXT file
def extract_text_from_txt(file_content):
    return file_content.decode('utf-8')

# Function to extract text from an image file
def extract_text_from_image(file_content):
    image = Image.open(io.BytesIO(file_content))
    return pytesseract.image_to_string(image)

# Function to extract text from a submission file based on file type
def extract_text_from_submission(file):
    file_url = file['fileurl']
    file_url_with_token = f"{file_url}&token={TOKEN}" if '?' in file_url else f"{file_url}?token={TOKEN}"
    file_content = download_file(file_url_with_token)
    file_name = file['filename'].lower()

    try:
        if file_name.endswith('.pdf'):
            return extract_text_from_pdf(file_content)
        elif file_name.endswith('.docx'):
            return extract_text_from_docx(file_content)
        elif file_name.endswith('.txt'):
            return extract_text_from_txt(file_content)
        elif file_name.endswith(('.png', '.jpg', '.jpeg')):
            return extract_text_from_image(file_content)
        else:
            return "Unsupported file format."
    except Exception as e:
        return f"Error extracting text: {str(e)}"

# Function to extract Q&A pairs using regex
def extract_qa_pairs(text):
    qa_pairs = re.findall(r'(Q\d+:\s.*?\nA\d+:\s.*?(?=\nQ\d+:|\Z))', text, re.DOTALL)
    return [pair.strip() for pair in qa_pairs]

# Function to send Q&A pair to grading endpoint and get response
def grade_qa_pair(qa_pair):
    url = "http://localhost:8000/api/ollamaAGA"  # Use your actual endpoint URL
    payload = {"query": qa_pair}
    headers = {"Content-Type": "application/json"}
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        result = response.json()
        justification = result.get("justification")
        scores = result.get("scores")
        return justification, scores
    else:
        raise Exception(f"Failed to grade Q&A pair: {response.status_code}, Response: {response.text}")

# Function to process submissions for a single user
def process_user_submissions(user, submissions_by_user):
    user_id = user['id']
    user_fullname = user['fullname']
    user_email = user['email']
    user_submission = submissions_by_user.get(user_id)
    
    if not user_submission:
        return {
            "Full Name": user_fullname,
            "User ID": user_id,
            "Email": user_email,
            "Submissions": []
        }
    
    graded_qa_pairs = []
    for plugin in user_submission['plugins']:
        if plugin['type'] == 'file':
            for filearea in plugin['fileareas']:
                for file in filearea['files']:
                    try:
                        text = extract_text_from_submission(file)
                        qa_pairs = extract_qa_pairs(text)
                        
                        for qa_pair in qa_pairs:
                            try:
                                justification, scores = grade_qa_pair(qa_pair)
                                graded_qa_pairs.append({
                                    "Q&A Pair": qa_pair,
                                    "Justification": justification,
                                    "Scores": scores
                                })
                            except Exception as e:
                                print(f"Error grading Q&A pair: {str(e)}")
                    except Exception as e:
                        print(f"Error extracting text for user {user_fullname}: {str(e)}")
    
    return {
        "Full Name": user_fullname,
        "User ID": user_id,
        "Email": user_email,
        "Submissions": graded_qa_pairs
    }

# Main function to get users, assignments, and extract text from submissions
def main(assignment_id=None, assignment_name=None):
    try:
        users = get_enrolled_users()
        assignments = get_assignments()
        
        assignment = None
        if assignment_id:
            assignment = next((a for a in assignments if a['id'] == assignment_id), None)
        elif assignment_name:
            assignment = next((a for a in assignments if a['name'].lower() == assignment_name.lower()), None)
        
        if not assignment:
            print("No assignments found.")
            return
        
        print(f"Assignment ID: {assignment['id']}, Name: {assignment['name']}")
        submissions = get_submissions(assignment['id'])
        submissions_by_user = {s['userid']: s for s in submissions}
        
        qa_dict = [
            process_user_submissions(user, submissions_by_user)
            for user in users
        ]
        
        print(qa_dict)
    except Exception as e:
        print(str(e))

if __name__ == '__main__':
    # Provide the assignment_id or assignment_name you want to target. One of the fields is enough to obtain the submissions.
    assignment_id = None  # Replace with specific assignment ID if needed
    assignment_name = 'EC1'  # Replace with specific assignment name if needed
    main(assignment_id=assignment_id, assignment_name=assignment_name)

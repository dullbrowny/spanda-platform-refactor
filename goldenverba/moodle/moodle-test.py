import requests
from docx import Document
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import re
import csv

# Replace with your Moodle instance URL and token
MOODLE_URL = 'http://localhost/moodle/moodle-4.2.1'
TOKEN = '80a42dd70578d1274a40e6994eafbb63'

# Function to make a Moodle API call
def moodle_api_call(params):
    endpoint = f'{MOODLE_URL}/webservice/rest/server.php'
    response = requests.get(endpoint, params=params)
    print(f"API Call to {params['wsfunction']} - Status Code: {response.status_code}")

    try:
        result = response.json()
    except ValueError as e:
        raise ValueError(f"Error parsing JSON response: {response.text}") from e

    if 'exception' in result:
        raise Exception(f"Error: {result['exception']['message']}")

    return result

# Function to get all courses
def get_all_courses():
    params = {
        'wstoken': TOKEN,
        'wsfunction': 'core_course_get_courses',
        'moodlewsrestformat': 'json'
    }
    return moodle_api_call(params)

# Function to get enrolled users in a specific course
def get_enrolled_users(course_id):
    params = {
        'wstoken': TOKEN,
        'wsfunction': 'core_enrol_get_enrolled_users',
        'moodlewsrestformat': 'json',
        'courseid': course_id
    }
    return moodle_api_call(params)

# Function to get assignments for a specific course
def get_assignments(course_id):
    params = {
        'wstoken': TOKEN,
        'wsfunction': 'mod_assign_get_assignments',
        'moodlewsrestformat': 'json',
        'courseids[0]': course_id
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
        avg_score = result.get("average_score")
        return justification, avg_score
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
            "Total Score": 0,
            "Feedback": "No submission"
        }
    
    total_score = 0
    all_comments = []

    for plugin in user_submission['plugins']:
        if plugin['type'] == 'file':
            for filearea in plugin['fileareas']:
                for file in filearea['files']:
                    try:
                        text = extract_text_from_submission(file)
                        qa_pairs = extract_qa_pairs(text)
                        
                        for qa_pair in qa_pairs:
                            try:
                                justification, avg_score = grade_qa_pair(qa_pair)
                                total_score += avg_score
                                all_comments.append(justification)
                            except Exception as e:
                                print(f"Error grading Q&A pair: {str(e)}")
                    except Exception as e:
                        print(f"Error extracting text for user {user_fullname}: {str(e)}")

    feedback = " | ".join(all_comments)
    return {
        "Full Name": user_fullname,
        "User ID": user_id,
        "Email": user_email,
        "Total Score": total_score,
        "Feedback": feedback
    }

# Function to write data to a CSV file in Moodle-compatible format
def write_to_csv(data, assignment_name, filename="submissions.csv"):
    with open(filename, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        
        # Write the header
        writer.writerow(["Full name", "Email address", assignment_name, "Feedback comments"])
        
        # Write the data
        for user_data in data:
            writer.writerow([
                user_data["Full Name"],
                user_data["Email"],
                user_data["Total Score"],
                user_data["Feedback"]
            ])

# Function to update grade for a user
def update_grade(user_id, assignment_id, grade, feedback):
    params = {
        'wstoken': TOKEN,
        'wsfunction': 'mod_assign_save_grade',
        'moodlewsrestformat': 'json',
        'assignmentid': assignment_id,
        'userid': user_id,
        'grade': grade,
        'attemptnumber': -1,  # Use -1 to grade the latest attempt
        'addattempt': 0,      # Set to 1 to create a new attempt, 0 to update the current one
        'workflowstate': 'graded',  # Set the state to 'graded'
        'plugindata[assignfeedbackcomments_editor][text]': feedback,  # Add feedback comments
        'plugindata[assignfeedbackcomments_editor][format]': 1  # Format for the feedback (1 = HTML)
    }
    result = moodle_api_call(params)
    return result

# Main function to get users, assignments, and extract text from submissions
def main(course_name, assignment_name):
    try:
        print("Fetching courses...")
        # Get all courses
        courses = get_all_courses()
        print(f"Found {len(courses)} courses.")
        
        # Find course ID based on course name
        course = next((c for c in courses if c['fullname'] == course_name), None)
        
        if not course:
            raise Exception("Course not found.")
        
        course_id = course['id']
        print(f"Course ID: {course_id}, Name: {course['fullname']}")

        print("Fetching enrolled users...")
        # Get enrolled users in the course
        users = get_enrolled_users(course_id)
        print(f"Found {len(users)} users.")

        print("Fetching assignments...")
        # Get assignments for the course
        assignments = get_assignments(course_id)
        print(f"Found {len(assignments)} assignments.")
        
        # Find assignment based on assignment name
        assignment = next((a for a in assignments if a['name'] == assignment_name), None)
        
        if not assignment:
            raise Exception("Assignment not found.")
        
        print(f"Assignment ID: {assignment['id']}, Name: {assignment['name']}")
        
        print("Fetching submissions...")
        # Get submissions for the assignment
        submissions = get_submissions(assignment['id'])
        print(f"Found {len(submissions)} submissions.")

        submissions_by_user = {submission['userid']: submission for submission in submissions}
        
        print("Processing submissions...")
        qa_dict = []
        for user in users:
            user_data = process_user_submissions(user, submissions_by_user)
            qa_dict.append(user_data)
        
        print("Writing results to CSV...")
        write_to_csv(qa_dict, assignment['name'])
        print("CSV file has been created.")
        
        print("Updating grades in Moodle...")
        for user_data in qa_dict:
            update_grade(user_data["User ID"], assignment['id'], user_data["Total Score"], user_data["Feedback"])
            print(f"Updated grade for user: {user_data['Full Name']}")

        print("Grades have been updated in Moodle.")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == '__main__':
    # Provide the course_name and assignment_name you want to target
    course_name = 'Introduction to computer science'  # Replace with specific course name
    assignment_name = 'EC1'  # Replace with specific assignment name
    main(course_name=course_name, assignment_name=assignment_name)

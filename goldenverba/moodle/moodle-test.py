
import requests
from docx import Document
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io
import re
import csv

# MOODLE_URL = 'https://taxila-spanda.wilp-connect.net/'
# TOKEN = '8175921296d9c56dec8de1bba4bec94e'
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

# Function to get enrolled users in a specific course
def get_enrolled_users(course_id):
    params = {
        'wstoken': TOKEN,
        'wsfunction': 'core_enrol_get_enrolled_users',
        'moodlewsrestformat': 'json',
        'courseid': course_id
    }
    return moodle_api_call(params)

def check_admin_capabilities():
    params = {
        'wstoken': TOKEN,
        'wsfunction': 'core_webservice_get_site_info',
        'moodlewsrestformat': 'json',
    }
    site_info = moodle_api_call(params)
    print("Site Info:", site_info)

# Function to get assignments for a specific course
def get_assignments(course_id):
    params = {
        'wstoken': TOKEN,
        'wsfunction': 'mod_assign_get_assignments',
        'moodlewsrestformat': 'json',
        'courseids[0]': course_id
    }
    assignments = moodle_api_call(params)
    
    # print("Assignments API Response:", assignments)  # Debug statement
    
    if not assignments.get('courses'):
        raise Exception("No courses found.")

    courses = assignments.get('courses', [])
    if not courses:
        print("No courses returned from API.")
        return []

    course_data = courses[0]

    if 'assignments' not in course_data:
        print(f"No assignments found for course: {course_data.get('fullname')}")
        return []

    return course_data['assignments']


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
    if not qa_pairs:
        return [text.strip()]
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
                        print(f"\nProcessing file: {file['filename']} for {user_fullname}...")
                        text = extract_text_from_submission(file)
                        qa_pairs = extract_qa_pairs(text)
                        
                        for i, qa_pair in enumerate(qa_pairs):
                            try:
                                justification, avg_score = grade_qa_pair(qa_pair)
                                total_score += avg_score
                                comment = f"Q{i+1}: {justification}"
                                all_comments.append(comment)

                                print(f"  Graded Q{i+1}: Avg. Score = {avg_score:.2f} - {justification}")
                                
                            except Exception as e:
                                print(f"  Error grading Q&A pair {i+1} for {user_fullname}: {str(e)}")
                    except Exception as e:
                        print(f"  Error extracting text for {user_fullname}: {str(e)}")

    feedback = " | ".join(all_comments)
    return {
        "Full Name": user_fullname,
        "User ID": user_id,
        "Email": user_email,
        "Total Score": total_score,
        "Feedback": feedback
    }

# Function to write data to a CSV file in Moodle-compatible format
def write_to_csv(data, course_id, assignment_name):
    filename = f"Course_{course_id}_{assignment_name.replace(' ', '_')}_autograded.csv"
    with open(filename, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        
        writer.writerow(["Full Name", "User ID", "Email", "Total Score", "Feedback"])
        
        for row in data:
            writer.writerow([row["Full Name"], row["User ID"], row["Email"], row["Total Score"], row["Feedback"]])

    print(f"Data successfully written to CSV file: {filename}")

# Function to update a user's grade in Moodle
def update_grade(user_id, assignment_id, grade, feedback):
    params = {
        'wstoken': TOKEN,
        'wsfunction': 'mod_assign_save_grade',
        'moodlewsrestformat': 'json',
        'assignmentid': assignment_id,
        'userid': user_id,
        'grade': grade,
        'feedback': feedback
    }
    response = moodle_api_call(params)
    print(f"Grade updated for User ID: {user_id}, Status: {response}")

# Main function to integrate with Moodle
def moodle_integration_pipeline(course_id, assignment_name):
    try:
        print(f"\nCourse ID: {course_id}")
        # Get enrolled users
        # print("\n=== Checking Admin Capabilities ===")
        # check_admin_capabilities()
        # Get enrolled users
        print("\n=== Fetching Enrolled Users ===")
        users = get_enrolled_users(course_id)
        print(f"Found {len(users)} enrolled users.")

        # Get assignments for the course
        print("\n=== Fetching Assignments ===")
        assignments = get_assignments(course_id)
        print(f"Found {len(assignments)} assignments.")

        assignment = next((a for a in assignments if a['name'].strip().lower() == assignment_name.strip().lower()), None)

        if not assignment:
            raise Exception("Assignment not found.")

        assignment_id = assignment['id']
        print(f"Assignment '{assignment_name}' found with ID: {assignment_id}")

        # Get submissions for the assignment
        print("\n=== Fetching Submissions ===")
        submissions = get_submissions(assignment_id)
        print(f"Found {len(submissions)} submissions.")

        submissions_by_user = {s['userid']: s for s in submissions}

        # Process submissions and extract text
        print("\n=== Processing Submissions ===")
        processed_data = [process_user_submissions(user, submissions_by_user) for user in users]

        # Write data to CSV
        print("\n=== Writing Data to CSV ===")
        write_to_csv(processed_data, course_id, assignment_name)

        # Update grades in Moodle (uncomment if needed)
        # print("Updating grades in Moodle...")
        # for user_data in processed_data:
        #     user_id = next(user['id'] for user in users if user['fullname'] == user_data['Full Name'])
        #     update_grade(user_id, assignment_id, user_data['Total Score'], user_data['Feedback'])

        print("\n=== Processing Completed Successfully ===")

    except Exception as e:
        print(f"\nAn error occurred: {str(e)}")

course_id = 2
assignment_name = "EC1"

moodle_integration_pipeline(course_id, assignment_name)

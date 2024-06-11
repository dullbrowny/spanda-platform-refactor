# Google Drive Ingestion Pipeline

This script automates the process of watching a Google Drive folder for changes, downloading files, and uploading them to a specified endpoint.

## Features
- **Authentication:** Securely authenticate with Google Drive using OAuth2.
- **Dynamic Folder ID:** Specify the Google Drive folder ID via command-line arguments for flexibility.
- **File Download and Upload:** Automatically download new files from Google Drive and upload them to a specified endpoint.
- **Error Handling:** Robust error handling to manage exceptions during the process.
- **Logging:** Comprehensive logging for better traceability and debugging.

## Prerequisites
- Python 3.6+
- Google Drive API credentials (OAuth2)

## Setup Instructions
### Clone the Repository
```bash
git clone <repository-url>
cd <repository-directory>
```

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Google Drive API Setup
1. Go to the Google Cloud Console.
2. Create a new project or select an existing project.
3. Enable the Google Drive API.
4. Create OAuth 2.0 Client IDs credentials and download the `credentials.json` file.
5. Place the `credentials.json` file in the root directory of the project.
6. Now,we can simply run the script
```bash
python Script.py
```


### Configuration
- **Logging:** The script uses Python's logging module to log messages. Logs can be customized by configuring the logging settings in the script.
- **Endpoint:** The script uploads files to the `/import` endpoint. Make sure your endpoint is up and running.

### Handling Credentials
- The script saves the OAuth2 token in a `token.json` file. 
- Add `token.json` and `credentials.json` to your `.gitignore` file to prevent them from being committed to the repository.

### Troubleshooting
- **Authentication Errors:** Ensure that your `credentials.json` file is correctly configured and placed in the root directory.
- **API Errors:** Check the logs for detailed error messages and verify that the Google Drive API is enabled and properly configured.
- **Network Issues:** Ensure that the endpoint you are uploading to is reachable and running.


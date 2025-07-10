# Google Docs Integration Setup

This guide will help you set up Google Docs integration for the PDF-to-Podcast application.

## Prerequisites

1. A Google account
2. Access to Google Cloud Console

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Google Docs API:
   - Go to "APIs & Services" > "Library"
   - Search for "Google Docs API"
   - Click on it and press "Enable"

## Step 2: Create Credentials

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "OAuth 2.0 Client IDs"
3. Choose "Desktop application" as the application type
4. Give it a name (e.g., "PDF-to-Podcast")
5. Click "Create"
6. Download the JSON file and rename it to `credentials.json`
7. Place `credentials.json` in the root directory of this project

## Step 3: First Run Authentication

When you first run the application with a Google Docs URL:

1. A browser window will open
2. Sign in with your Google account
3. Grant permission to access your Google Docs
4. The application will save the authentication token for future use

## Step 4: Using Google Docs URLs

You can now use Google Docs URLs in the application:

- **Full URL**: `https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit`
- **Short URL**: `https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms`
- **Document ID**: `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms`

## Security Notes

- The `credentials.json` file contains sensitive information - don't commit it to version control
- The `token.json` file contains your authentication tokens - it will be created automatically
- Both files are already in `.gitignore` to prevent accidental commits

## Troubleshooting

### "Credentials file not found"
- Make sure `credentials.json` is in the project root directory
- Verify the file name is exactly `credentials.json`

### "Permission denied"
- Make sure the Google Docs document is shared with your Google account
- Check that you have at least "View" permissions

### "No text content found"
- The document might be empty or contain only images
- Try with a document that has text content

## Example Usage

1. Open the application
2. Paste a Google Docs URL in the "Google Docs URL" field
3. Enter your OpenAI API key (if not set as environment variable)
4. Click "Submit"
5. Wait for the podcast to be generated! 
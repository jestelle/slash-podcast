import os
import re
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, parse_qs

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from loguru import logger


class GoogleDocsClient:
    """Client for interacting with Google Docs API"""
    
    # If modifying these scopes, delete the file token.json.
    SCOPES = ['https://www.googleapis.com/auth/documents.readonly']
    
    def __init__(self, credentials_path: Optional[str] = None, redirect_uri: Optional[str] = None):
        self.credentials_path = credentials_path or 'credentials.json'
        self.redirect_uri = redirect_uri or 'http://localhost:7860/oauth2callback'
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Docs API"""
        creds = None
        # The file token.json stores the user's access and refresh tokens
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', self.SCOPES)
        
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"Credentials file '{self.credentials_path}' not found. "
                        "Please download it from Google Cloud Console."
                    )
                
                # For web applications, we need to handle OAuth differently
                # This will be handled by the web interface
                raise Exception(
                    "OAuth authentication required. Please use the web interface to authenticate."
                )
        
        self.service = build('docs', 'v1', credentials=creds)
        logger.info("Successfully authenticated with Google Docs API")
    
    def create_oauth_url(self) -> str:
        """Create OAuth URL for web application"""
        if not os.path.exists(self.credentials_path):
            raise FileNotFoundError(f"Credentials file '{self.credentials_path}' not found.")
        
        flow = Flow.from_client_secrets_file(
            self.credentials_path,
            scopes=self.SCOPES,
            redirect_uri=self.redirect_uri
        )
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        
        return authorization_url
    
    def exchange_code_for_token(self, authorization_code: str) -> None:
        """Exchange authorization code for access token"""
        if not os.path.exists(self.credentials_path):
            raise FileNotFoundError(f"Credentials file '{self.credentials_path}' not found.")
        
        flow = Flow.from_client_secrets_file(
            self.credentials_path,
            scopes=self.SCOPES,
            redirect_uri=self.redirect_uri
        )
        
        flow.fetch_token(code=authorization_code)
        
        # Save the credentials
        with open('token.json', 'w') as token:
            token.write(flow.credentials.to_json())
        
        self.service = build('docs', 'v1', credentials=flow.credentials)
        logger.info("Successfully authenticated with Google Docs API")
    
    def extract_doc_id_from_url(self, url: str) -> Optional[str]:
        """Extract document ID from Google Docs URL"""
        # Handle different Google Docs URL formats
        patterns = [
            r'/document/d/([a-zA-Z0-9-_]+)',  # Standard format
            r'/document/d/([a-zA-Z0-9-_]+)/edit',  # Edit format
            r'/document/d/([a-zA-Z0-9-_]+)/view',  # View format
            r'id=([a-zA-Z0-9-_]+)',  # Query parameter format
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        # If no pattern matches, assume the URL itself is the doc ID
        if re.match(r'^[a-zA-Z0-9-_]+$', url):
            return url
        
        return None
    
    def get_document_text(self, doc_id: str) -> str:
        """Fetch document content and convert to plain text"""
        try:
            document = self.service.documents().get(documentId=doc_id).execute()
            return self._extract_text_from_document(document)
        except HttpError as error:
            logger.error(f"Error fetching document {doc_id}: {error}")
            raise
    
    def _extract_text_from_document(self, document: dict) -> str:
        """Extract plain text from Google Docs document structure"""
        text_parts = []
        
        if 'body' in document and 'content' in document['body']:
            for element in document['body']['content']:
                if 'paragraph' in element:
                    text_parts.append(self._extract_text_from_paragraph(element['paragraph']))
        
        return '\n\n'.join(text_parts)
    
    def _extract_text_from_paragraph(self, paragraph: dict) -> str:
        """Extract text from a paragraph element"""
        text_parts = []
        
        if 'elements' in paragraph:
            for element in paragraph['elements']:
                if 'textRun' in element:
                    text_parts.append(element['textRun']['content'])
        
        return ''.join(text_parts)
    
    def get_recent_documents(self, max_results: int = 10) -> List[dict]:
        """Get list of recent Google Docs documents"""
        try:
            # Note: This requires the Drive API scope, which we don't have yet
            # For now, we'll return a placeholder
            logger.warning("Getting recent documents requires Drive API scope")
            return []
        except HttpError as error:
            logger.error(f"Error fetching recent documents: {error}")
            return []


def extract_text_from_google_docs(url_or_id: str, credentials_path: Optional[str] = None) -> str:
    """Convenience function to extract text from a Google Docs document"""
    try:
        client = GoogleDocsClient(credentials_path)
        
        # Extract document ID from URL or use as-is
        doc_id = client.extract_doc_id_from_url(url_or_id)
        if not doc_id:
            raise ValueError(f"Could not extract document ID from: {url_or_id}")
        
        return client.get_document_text(doc_id)
    except Exception as e:
        if "OAuth authentication required" in str(e):
            raise Exception(
                "Google Docs authentication required. Please authenticate first using the web interface."
            )
        raise e


def create_google_oauth_url(credentials_path: Optional[str] = None) -> str:
    """Create OAuth URL for Google Docs authentication"""
    client = GoogleDocsClient(credentials_path)
    return client.create_oauth_url()


def authenticate_google_docs(authorization_code: str, credentials_path: Optional[str] = None) -> None:
    """Authenticate with Google Docs using authorization code"""
    client = GoogleDocsClient(credentials_path)
    client.exchange_code_for_token(authorization_code) 
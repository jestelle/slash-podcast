import concurrent.futures as cf
import glob
import io
import os
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import List, Literal, Union

import gradio as gr
import sentry_sdk
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loguru import logger
from openai import OpenAI, RateLimitError
from promptic import llm
from pydantic import BaseModel, ValidationError
from pypdf import PdfReader
from tenacity import retry, retry_if_exception_type, wait_exponential, stop_after_attempt

from google_docs import extract_text_from_google_docs, create_google_oauth_url, authenticate_google_docs


if sentry_dsn := os.getenv("SENTRY_DSN"):
    sentry_sdk.init(sentry_dsn)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

# OAuth callback route
@app.get("/oauth2callback")
async def oauth_callback(code: str = None, error: str = None):
    """Handle OAuth callback from Google"""
    if error:
        return {"error": error}
    
    if not code:
        return {"error": "No authorization code received"}
    
    try:
        authenticate_google_docs(code)
        return {
            "success": True,
            "message": "Successfully authenticated with Google Docs! You can now close this window and return to the main application."
        }
    except Exception as e:
        return {"error": f"Authentication failed: {str(e)}"}


class DialogueItem(BaseModel):
    text: str
    speaker: Literal["female-1", "male-1", "female-2"]

    @property
    def voice(self):
        return {
            "female-1": "alloy",
            "male-1": "onyx",
            "female-2": "shimmer",
        }[self.speaker]


class Dialogue(BaseModel):
    scratchpad: str
    dialogue: List[DialogueItem]


@retry(
    retry=retry_if_exception_type(RateLimitError),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(5)
)
def get_mp3(text: str, voice: str, api_key: str = None) -> bytes:
    client = OpenAI(
        api_key=api_key or os.getenv("OPENAI_API_KEY"),
    )

    with client.audio.speech.with_streaming_response.create(
        model="tts-1",
        voice=voice,
        input=text,
    ) as response:
        with io.BytesIO() as file:
            for chunk in response.iter_bytes():
                file.write(chunk)
            return file.getvalue()


def check_google_auth_status():
    """Check if user is authenticated with Google Docs"""
    try:
        # Try to create a client - this will fail if not authenticated
        from google_docs import GoogleDocsClient
        client = GoogleDocsClient()
        return "✅ Authenticated with Google Docs"
    except Exception as e:
        if "OAuth authentication required" in str(e) or "Credentials file" in str(e):
            return "❌ Not authenticated with Google Docs"
        else:
            return f"❌ Error: {str(e)}"


def get_google_auth_url():
    """Get Google OAuth URL for authentication"""
    try:
        auth_url = create_google_oauth_url()
        return f"""
        🔗 **Click the link below to authenticate with Google Docs:**
        
        [**Authenticate with Google Docs**]({auth_url})
        
        After clicking, you'll be redirected to Google's authorization page. 
        Once you authorize, you'll be redirected back to this application.
        """
    except Exception as e:
        return f"❌ Error creating auth URL: {str(e)}"


def handle_google_auth_callback(auth_code: str):
    """Handle OAuth callback with authorization code"""
    try:
        authenticate_google_docs(auth_code)
        return "✅ Successfully authenticated with Google Docs!"
    except Exception as e:
        return f"❌ Authentication failed: {str(e)}"


def generate_audio_from_inputs(pdf_file, google_docs_url: str, openai_api_key: str = None):
    """Wrapper function to handle both PDF files and Google Docs URLs"""
    
    # Determine which input to use
    if google_docs_url and google_docs_url.strip():
        # Use Google Docs URL
        return generate_audio(google_docs_url.strip(), openai_api_key)
    elif pdf_file:
        # Use PDF file
        return generate_audio(pdf_file.name, openai_api_key)
    else:
        raise gr.Error("Please provide either a PDF file or a Google Docs URL")


def generate_audio(file_or_url: Union[str, Path], openai_api_key: str = None) -> bytes:

    if not (os.getenv("OPENAI_API_KEY") or openai_api_key):
        raise gr.Error("OpenAI API key is required")

    # Determine if input is a Google Docs URL or a file path
    file_or_url_str = str(file_or_url)
    
    if file_or_url_str.startswith(('http://', 'https://')) and 'docs.google.com' in file_or_url_str:
        # Handle Google Docs URL
        try:
            logger.info(f"Processing Google Docs URL: {file_or_url_str}")
            text = extract_text_from_google_docs(file_or_url_str)
            if not text.strip():
                raise gr.Error("No text content found in the Google Docs document")
        except Exception as e:
            logger.error(f"Error processing Google Docs: {e}")
            raise gr.Error(f"Failed to process Google Docs: {str(e)}")
    else:
        # Handle PDF file
        try:
            with Path(file_or_url).open("rb") as f:
                reader = PdfReader(f)
                text = "\n\n".join([page.extract_text() for page in reader.pages])
            if not text.strip():
                raise gr.Error("No text content found in the PDF")
        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
            raise gr.Error(f"Failed to process PDF: {str(e)}")

    @retry(retry=retry_if_exception_type(ValidationError))
    @llm(
        model="gpt-4o",
        api_key=openai_api_key or os.getenv("OPENAI_API_KEY"),
    )
    def generate_dialogue(text: str) -> Dialogue:
        """
        Your task is to take the input text provided and turn it into an engaging, informative podcast dialogue. The input text may be messy or unstructured, as it could come from a variety of sources like PDFs or web pages. Don't worry about the formatting issues or any irrelevant information; your goal is to extract the key points and interesting facts that could be discussed in a podcast.

        Here is the input text you will be working with:

        <input_text>
        {text}
        </input_text>

        First, carefully read through the input text and identify the main topics, key points, and any interesting facts or anecdotes. Think about how you could present this information in a fun, engaging way that would be suitable for an audio podcast.

        <scratchpad>
        Brainstorm creative ways to discuss the main topics and key points you identified in the input text. Consider using analogies, storytelling techniques, or hypothetical scenarios to make the content more relatable and engaging for listeners.

        Keep in mind that your podcast should be accessible to a general audience, so avoid using too much jargon or assuming prior knowledge of the topic. If necessary, think of ways to briefly explain any complex concepts in simple terms.

        Use your imagination to fill in any gaps in the input text or to come up with thought-provoking questions that could be explored in the podcast. The goal is to create an informative and entertaining dialogue, so feel free to be creative in your approach.

        Write your brainstorming ideas and a rough outline for the podcast dialogue here. Be sure to note the key insights and takeaways you want to reiterate at the end.
        </scratchpad>

        Now that you have brainstormed ideas and created a rough outline, it's time to write the actual podcast dialogue. Aim for a natural, conversational flow between the host and any guest speakers. Incorporate the best ideas from your brainstorming session and make sure to explain any complex topics in an easy-to-understand way.

        <podcast_dialogue>
        Write your engaging, informative podcast dialogue here, based on the key points and creative ideas you came up with during the brainstorming session. Use a conversational tone and include any necessary context or explanations to make the content accessible to a general audience. Use made-up names for the hosts and guests to create a more engaging and immersive experience for listeners. Do not include any bracketed placeholders like [Host] or [Guest]. Design your output to be read aloud -- it will be directly converted into audio.

        Make the dialogue as long and detailed as possible, while still staying on topic and maintaining an engaging flow. Aim to use your full output capacity to create the longest podcast episode you can, while still communicating the key information from the input text in an entertaining way.

        At the end of the dialogue, have the host and guest speakers naturally summarize the main insights and takeaways from their discussion. This should flow organically from the conversation, reiterating the key points in a casual, conversational manner. Avoid making it sound like an obvious recap - the goal is to reinforce the central ideas one last time before signing off.
        </podcast_dialogue>
        """

    llm_output = generate_dialogue(text)

    audio = b""
    transcript = ""

    characters = 0

    # Process audio sequentially to avoid rate limits
    for line in llm_output.dialogue:
        transcript_line = f"{line.speaker}: {line.text}"
        logger.info(f"Generating audio for: {line.speaker}")
        
        try:
            audio_chunk = get_mp3(line.text, line.voice, openai_api_key)
            audio += audio_chunk
            transcript += transcript_line + "\n\n"
            characters += len(line.text)
            
            # Add a small delay between requests to avoid rate limits
            time.sleep(0.2)  # 200ms delay between requests
            
        except Exception as e:
            logger.error(f"Error generating audio for {line.speaker}: {e}")
            # Continue with next line instead of failing completely
            transcript += f"{transcript_line} [AUDIO GENERATION FAILED]\n\n"

    logger.info(f"Generated {characters} characters of audio")

    temporary_directory = "./gradio_cached_examples/tmp/"
    os.makedirs(temporary_directory, exist_ok=True)

    # we use a temporary file because Gradio's audio component doesn't work with raw bytes in Safari
    temporary_file = NamedTemporaryFile(
        dir=temporary_directory,
        delete=False,
        suffix=".mp3",
    )
    temporary_file.write(audio)
    temporary_file.close()

    # Delete any files in the temp directory that end with .mp3 and are over a day old
    for file in glob.glob(f"{temporary_directory}*.mp3"):
        if os.path.isfile(file) and time.time() - os.path.getmtime(file) > 24 * 60 * 60:
            os.remove(file)

    return temporary_file.name, transcript


# Create the main interface
with gr.Blocks(title="PDF to Podcast", theme="origin") as demo:
    gr.HTML(Path("description.md").read_text())
    
    # Google Docs Authentication Section
    with gr.Accordion("🔐 Google Docs Authentication", open=False):
        gr.Markdown("""
        **To use Google Docs, you need to authenticate first:**
        1. Click "Check Auth Status" to see if you're already authenticated
        2. If not authenticated, click "Get Auth URL" to get the authorization link
        3. Click the link to authorize with Google
        4. You'll be redirected back automatically after authorization
        """)
        
        with gr.Row():
            auth_status_btn = gr.Button("Check Auth Status", variant="secondary")
            auth_url_btn = gr.Button("Get Auth URL", variant="secondary")
        
        auth_status_output = gr.Markdown("Click 'Check Auth Status' to see your authentication status")
        auth_url_output = gr.Markdown("Click 'Get Auth URL' to get the authorization link")
    
    # Main Content Section
    with gr.Row():
        with gr.Column():
            pdf_file = gr.File(
                label="PDF File (optional)",
                visible=True,
            )
            google_docs_url = gr.Textbox(
                label="Google Docs URL (optional)",
                placeholder="https://docs.google.com/document/d/...",
                visible=True,
            )
            openai_api_key = gr.Textbox(
                label="OpenAI API Key",
                visible=not os.getenv("OPENAI_API_KEY"),
            )
            submit_btn = gr.Button("Generate Podcast", variant="primary")
        
        with gr.Column():
            audio_output = gr.Audio(label="Audio", format="mp3")
            transcript_output = gr.Textbox(label="Transcript", lines=10)
    
    # Examples
    gr.Examples(
        examples=[[str(p), "", None] for p in Path("examples").glob("*.pdf")],
        inputs=[pdf_file, google_docs_url, openai_api_key]
    )
    
    # Event handlers
    auth_status_btn.click(
        fn=check_google_auth_status,
        outputs=auth_status_output
    )
    
    auth_url_btn.click(
        fn=get_google_auth_url,
        outputs=auth_url_output
    )
    
    submit_btn.click(
        fn=generate_audio_from_inputs,
        inputs=[pdf_file, google_docs_url, openai_api_key],
        outputs=[audio_output, transcript_output]
    )


# Configure the demo
demo.queue(
    max_size=20,
    default_concurrency_limit=20,
)

# Mount the app
app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    demo.launch(show_api=False)

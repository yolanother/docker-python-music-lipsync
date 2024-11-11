import io
import time
import runpod
import requests
import os
import base64
import tempfile
from runpod.serverless.utils import rp_upload
from pydub import AudioSegment
import traceback

def log(message):
    """ Logs a message to the console. """
    print(f"runpod-worker-lipsync - {message}")

def save_audio_from_base64(encoded_data, save_path):
    """ Saves base64-encoded audio data to a specified path. """
    try:
        # Decode the base64-encoded data
        decoded_data = base64.b64decode(encoded_data)

        # Create a file-like object from the decoded data
        audio_stream = io.BytesIO(decoded_data)

        # Load the audio from the file-like object
        audio = AudioSegment.from_file(audio_stream)

        # Export the audio as a WAV file
        with open(save_path, 'wb') as audio_file:
            audio.export(audio_file.name, format="wav")
        return save_path, None
    except Exception as e:
        # pint stack trace
        traceback.print_exc()
        return None, str(e)

def download_audio(url, download_path):
    """ Downloads audio from a given URL to a specified path. """
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(download_path, 'wb') as audio_file:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        audio_file.write(chunk)
            return download_path, None
        else:
            return None, f"Failed to download audio. Status code: {response.status_code}"
    except Exception as e:
        return None, str(e)

def check_server(url, retries=500, delay=50):
    """
    Check if a server is reachable via HTTP GET request

    Args:
    - url (str): The URL to check
    - retries (int, optional): The number of times to attempt connecting to the server. Default is 50
    - delay (int, optional): The time in milliseconds to wait between retries. Default is 500

    Returns:
    bool: True if the server is reachable within the given number of retries, otherwise False
    """
    
    for i in range(retries):
        try:
            response = requests.get(url)
    
            # If the response status code is 200, the server is up and running
            if response.status_code == 200:
                log(f"API is reachable after {(i + 1) * delay} ms.")
                return True
        except requests.RequestException as e:
            # If an exception occurs, the server may not be ready
            pass
    
        # Log message every 5 seconds
        if (i + 1) % (5000 // delay) == 0:
            print("Still waiting on the server to come up...")
    
        # Wait for the specified delay before retrying
        time.sleep(delay / 1000)

    print(
        f"runpod-worker-comfy - Failed to connect to server at {url} after {retries} attempts."
    )
    return False

def process_uploaded_file(job_id, file_path, transcript, output_format="pcm"):
    """ Sends the uploaded file to the processing endpoint. """
    try:
        with open(file_path, 'rb') as file:
            # set the post accept to be json
            headers = {
                "accept": "application/json"
            }
            log(f"Processing file {file_path} with transcript: {transcript}")
            response = requests.post(
                'http://localhost:8000/analyze/',
                headers=headers,
                files={'file': ('audio.wav', file, 'audio/wav')},
                data={'transcript': transcript, 'include_base64': True, "output_format": output_format}
            )

            if response.status_code == 200:
                json = response.json()
                if os.environ.get("BUCKET_ENDPOINT_URL", False):
                    # write response.content to a file so we can upload it to S3 use NamedTemporaryFile
                    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                        temp_filename = temp_file.name
                        temp_file.write(response.content)
                        file = temp_file.name
                    # URL to image in AWS S3
                    data_encoded_audio_url = rp_upload.files(job_id, [file])
                    # write the json["data"] to a file so we can upload it to S3
                    with open(file, 'wb') as f:
                        f.write(json["data"])
                    # URL to data in AWS S3
                    data_url = rp_upload.files(job_id, [file])
                    os.remove(file)
                    return {"data_encoded_audio_url": data_encoded_audio_url, "data_url": data_url}, None
                else:
                    return json, None
            else:
                return None, f"Processing failed with status code: {response.status_code}"
    except Exception as e:
        return None, str(e)

def handler(job):
    """ Handler function that will be used to process jobs. """
    job_input = job['input']
    id = job['id']

    audio_base64 = job_input.get('data')
    url = job_input.get('url')
    transcript = job_input.get('transcript', job_input.get('lyrics', ""))
    output_format = job_input.get('output_format', job_input.get('output_audio_format', "pcm"))

    log(f"Processing job {id}")
    log(f"Title: {job_input.get('title', 'Untitled')}")
    log(f"Lyrics: {transcript}")
    log(f"Output format: {output_format}")
    log(f"Mime type: {job_input.get('mime_type', 'Unknown')}")

    # If we have base64 audio output the fist 20 and last 20 characters with ... between
    if audio_base64:
        log(f"Base64 audio: {audio_base64[:20]}...{audio_base64[-20:]}")
    # If we have a URL output the first 20 and last 20 characters with ... between
    if url:
        log(f"URL: {url}")

    check_server('http://localhost:8000/docs', retries=50, delay=500)

    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_filename = temp_file.name

    try:
        if audio_base64:
            saved_file, error = save_audio_from_base64(audio_base64, temp_filename)
            if saved_file:
                response_data, error = process_uploaded_file(id, saved_file, transcript, output_format)
                if response_data:
                    # if submit url is in job input's submit field
                    if job_input.get('submit', False):
                        # submit the data to the submit url
                        submit_url = job_input['submit_post_url']
                        requests.post(submit_url, json=response_data)

                    return {
                        "id": id,
                        "message": "Audio file successfully processed from base64 data.",
                        "data": response_data
                    }
                else:
                    return {"error": f"Failed to process audio file: {error}"}
            else:
                return {"error": f"Failed to save audio from base64 data: {error}"}
        elif url:
            downloaded_file, error = download_audio(url, temp_filename)
            if downloaded_file:
                response_data, error = process_uploaded_file(id, downloaded_file, transcript, output_format)
                if response_data:
                    return {
                        "id": id,
                        "message": "Audio file successfully downloaded and processed.",
                        "data": response_data
                    }
                else:
                    return {"error": f"Failed to process audio file: {error}"}
            else:
                return {"error": f"Failed to download audio file: {error}"}
        else:
            return {"error": "No URL or base64-encoded audio provided in input."}
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

runpod.serverless.start({"handler": handler})

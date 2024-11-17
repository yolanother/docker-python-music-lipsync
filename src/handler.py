import io
import json
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

        save_path_mp3 = save_path.replace(".wav", ".mp3")
        # if no mp3 extension was added add one
        if save_path_mp3 == save_path:
            save_path_mp3 += ".mp3"

        # Export the audio as a WAV file
        with open(save_path, 'wb') as audio_file:
            audio.export(audio_file.name, format="wav")
        with open(save_path_mp3, 'wb') as audio_file:
            audio.export(audio_file.name, format="mp3")
        return save_path, save_path_mp3, None
    except Exception as e:
        # pint stack trace
        traceback.print_exc()
        return None, str(e)

def download_audio(url, download_path):
    """Downloads audio from a given URL, saves it as a WAV file at the specified path."""
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            # Load the downloaded audio into a BytesIO buffer
            audio_data = io.BytesIO()
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    audio_data.write(chunk)
            
            # Move back to the start of the BytesIO buffer
            audio_data.seek(0)

            # Convert the audio data to WAV format and save it
            audio = AudioSegment.from_file(audio_data)
            audio.export(download_path, format="wav")

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

def process_uploaded_file(upload):
    """ Sends the uploaded file to the processing endpoint. """
    try:
        job_id = upload.get("id")
        saved_file = upload.get("saved_file")
        save_file_mp3 = upload.get("save_file_mp3")
        url = upload.get("url")
        transcript = upload.get("transcript")
        output_format = upload.get("output_format")
        sample_rate = upload.get("sample_rate")
        channels = upload.get("channels")
        upload_mp3 = upload.get("upload_mp3", False)

        if upload_mp3 and url is None and os.environ.get("BUCKET_ENDPOINT_URL", False) and save_file_mp3 is not None:
            [upload_url] = rp_upload.files(job_id, [save_file_mp3])
            url = upload_url
            log("Uploaded source audio to bucket: " + str(url))
    
        with open(saved_file, 'rb') as file:
            # set the post accept to be json
            headers = {
                "accept": "application/json"
            }
            response = requests.post(
                'http://localhost:8000/analyze/',
                headers=headers,
                files={'file': ('audio.wav', file, 'audio/wav')},
                data={'transcript': transcript, 'include_base64': True, "output_format": output_format, "sample_rate": sample_rate, "channels": channels}
            )

            if response.status_code == 200:
                jsonResponse = response.json()
                if os.environ.get("BUCKET_ENDPOINT_URL", False):
                    log("Uploading to bucket: " + str(os.environ.get("BUCKET_ENDPOINT_URL", False)))

                    data_encoded_audio_file = f"{job_id}.{output_format}v"
                    data_file = f"{job_id}.json"
                    # Write the response to a file
                    with open(data_encoded_audio_file, 'wb') as f:
                        base64EncodeData = jsonResponse['data_encoded_audio']
                        f.write(base64.b64decode(base64EncodeData))
                    with open(data_file, 'w', encoding='utf-8') as f:
                        # Convert the JSON data to a string
                        jsonString = json.dumps(jsonResponse['data'], ensure_ascii=False, indent=2)
                        f.write(jsonString)
                    
                    [data_encoded_audio_url, data_url] = rp_upload.files(job_id, [data_encoded_audio_file, data_file])
                    data = {"data_encoded_audio_url": data_encoded_audio_url, "data_url": data_url, "mp3_url": url}, None
                    log(f"Uploaded to bucket: {data}")
                    return data
                else:
                    return json, None
            else:
                return None, f"Processing failed with status code: {response.status_code}"
    except Exception as e:
        traceback.print_exc()
        return None, str(e)
    
def submit(job_input, response_data):
    # if submit url is in job input's submit field
    if job_input.get('submit', False):
        # submit the data to the submit url
        submit_url = job_input['submit']
        log(f"Submitting data to {submit_url}")
        result = requests.post(submit_url, json=response_data)
        log(f"Submitted data to {submit_url} with status code {result.status_code}\n{result.text}")

def handler(job):
    """ Handler function that will be used to process jobs. """
    job_input = job['input']
    id = job['id']

    audio_base64 = job_input.get('data')
    url = job_input.get('url')
    transcript = job_input.get('transcript', job_input.get('lyrics', ""))
    output_format = job_input.get('output_format', job_input.get('output_audio_format', "pcm"))
    upload_mp3 = job_input.get('upload_mp3', False)

    log(f"Processing job {id}")
    log(f"Title: {job_input.get('title', 'Untitled')}")
    log(f"Lyrics: {transcript}")
    log(f"Output format: {output_format}")
    log(f"Mime type: {job_input.get('mime', 'Unknown')}")

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
            saved_file, save_file_mp3, error = save_audio_from_base64(audio_base64, temp_filename)
            upload = {
                "id": id,
                "saved_file": saved_file,
                "save_file_mp3": save_file_mp3,
                "transcript": transcript,
                "output_format": output_format,
                "sample_rate": 24000,
                "channels": 1,
                "url": url,
                "upload_mp3": upload_mp3
            }
            if saved_file:
                response_data, error = process_uploaded_file(upload)
                if response_data:
                    log(f"Processed audio file from base64 data.")
                    submit(job_input, response_data)

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
            upload = {
                "id": id,
                "saved_file": downloaded_file,
                "url": url,
                "transcript": transcript,
                "output_format": output_format,
                "sample_rate": 24000,
                "channels": 1,
            }
            if downloaded_file:
                response_data, error = process_uploaded_file(upload)
                if response_data:
                    log(f"Downloaded and processed audio file from URL.")
                    submit(job_input, response_data)
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

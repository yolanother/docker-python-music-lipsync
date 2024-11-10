import runpod
import requests
import os
import base64
import tempfile

def save_audio_from_base64(encoded_data, save_path):
    """ Saves base64-encoded audio data to a specified path. """
    try:
        with open(save_path, 'wb') as audio_file:
            audio_file.write(base64.b64decode(encoded_data))
        return save_path, None
    except Exception as e:
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

def process_uploaded_file(file_path, transcript):
    """ Sends the uploaded file to the processing endpoint. """
    try:
        with open(file_path, 'rb') as file:
            response = requests.post(
                'http://localhost:8000/analyze/',
                files={'file': ('audio.wav', file, 'audio/wav')},
                data={'transcript': transcript}
            )
            if response.status_code == 200:
                base64_encoded_data = base64.b64encode(response.content).decode('utf-8')
                return base64_encoded_data, None
            else:
                return None, f"Processing failed with status code: {response.status_code}"
    except Exception as e:
        return None, str(e)

def handler(job):
    """ Handler function that will be used to process jobs. """
    job_input = job['input']

    audio_base64 = job_input.get('data')
    url = job_input.get('url')
    transcript = job_input.get('transcript', job_input.get('lyrics', ""))

    # Create a temporary file
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_filename = temp_file.name

    try:
        if audio_base64:
            saved_file, error = save_audio_from_base64(audio_base64, temp_filename)
            if saved_file:
                response_data, error = process_uploaded_file(saved_file, transcript)
                if response_data:
                    return {
                        "message": "Audio file successfully processed from base64 data.",
                        "vismedata": response_data
                    }
                else:
                    return {"error": f"Failed to process audio file: {error}"}
            else:
                return {"error": f"Failed to save audio from base64 data: {error}"}
        elif url:
            downloaded_file, error = download_audio(url, temp_filename)
            if downloaded_file:
                response_data, error = process_uploaded_file(downloaded_file, transcript)
                if response_data:
                    return {
                        "message": "Audio file successfully downloaded and processed.",
                        "vismedata": response_data
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

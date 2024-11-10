import base64
import json
import mimetypes
import uuid
import sys

def convert_file_to_json(file_path):
    # Generate a unique ID
    file_id = str(uuid.uuid4())
    
    # Get MIME type of the file
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "application/octet-stream"
    
    # Read and encode the file in base64
    with open(file_path, 'rb') as file:
        encoded_data = base64.b64encode(file.read()).decode('utf-8')
    
    # Create the JSON structure
    json_structure = {
        "id": file_id,
        "input": {
            "mime": mime_type,
            "data": encoded_data
        }
    }
    
    # Convert to JSON string
    json_output = json.dumps(json_structure, indent=4)
    
    # Save JSON to a file
    with open('test_input.json', 'w') as json_file:
        json_file.write(json_output)
    
    return json_output

def main():
    if len(sys.argv) != 2:
        print("Usage: python script.py <file_path>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    result_json = convert_file_to_json(file_path)
    print("JSON saved to test_input.json")

if __name__ == "__main__":
    main()

from flask import Flask, request, jsonify
import requests
from urllib.parse import urlparse
from dateutil.parser import parse as parse_date
import json
import threading
import openai

app = Flask(__name__)

# Set your OpenAI API key securely, and ensure it's not hardcoded in production
openai.api_key = os.getenv('OPENAI_API_KEY')

# Initial state
state = {
    "question": None,
    "documents": [],
    "factsByDay": {},
    "status": "idle"  # 'idle', 'processing', 'done'
}

def fetch_content_from_url(url):
    """Fetch and return content from the specified URL."""
    response = requests.get(url)
    response.raise_for_status()
    return response.text
def generate_response(question,document_urls):
    prompt = f"""You are tasked extracting relevant information following the {question} from call logs {document_urls} for team decisions. extract the relevant decisions made by the team. Use only information from the {document_urls}.
    "Question" : “What product design decisions did the team make?”
    "Logs" : "00:00:10 - Alex: Let's choose our app's color scheme today.
        00:00:36 - Jordan: I suggest blue for a calm feel.
        00:00:51 - Casey: We need to make sure it's accessible to all users.""
    Given a question and call log in the format above, your AI system should be able to identify and extract the product design decisions discussed by the team. For instance, based on the provided example, the system should output:
        + The team will use blue for the color scheme of the app.
        + The team will make the app accessible to all users.
    Use bullet point template for the answer.
    """    
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo-1106",
        messages=[
    {
      "role": "system",
      "content": prompt
    }
  ],
        temperature=0.5,
        max_tokens=256,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
    )
    return response.choices[0].message.content.strip()

def process_document(question, url):
    """Process a single document: fetch content, generate a response, and extract facts."""
    document_content = fetch_content_from_url(url)
    response = generate_response(question, document_content)
    date = parse_date(urlparse(url).path.split('_')[2]).strftime("%Y-%m-%d")
    if date not in state["factsByDay"]:
        state["factsByDay"][date] = []
    # Assuming the response directly contains the facts
    state["factsByDay"][date].append(response)

def process_documents():
    """Process all documents and update the state upon completion."""
    global state
    state["status"] = "processing"
    for url in state["documents"]:
        process_document(state["question"], url)
    state["status"] = "done"

@app.route('/submit_question_and_documents', methods=['POST'])
def submit_question_and_documents():
    global state
    data = request.json
    state["question"] = data.get("question")
    state["documents"] = data.get("documents", [])
    state["factsByDay"] = {}
    state["status"] = "idle"
    # Process documents in a background thread to prevent blocking
    threading.Thread(target=process_documents).start()
    return jsonify({"message": "Processing started"}), 200

@app.route('/get_question_and_facts', methods=['GET'])
def get_question_and_facts():
    if state["status"] == "processing":
        return jsonify({"question": state["question"], "status": "processing"}), 200
    elif state["status"] == "done":
        return jsonify({
            "question": state["question"],
            "factsByDay": state["factsByDay"],
            "status": "done"
        }), 200
    else:
        return jsonify({"message": "No processing in progress or started"}), 400

if __name__ == '__main__':
    app.run(debug=False, port=5000)
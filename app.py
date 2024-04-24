import streamlit as st
import openai
from datetime import datetime
import requests
from urllib.parse import urlparse
from dateutil.parser import parse as parse_date
import json
from json.decoder import JSONDecodeError
import os


# Set your OpenAI API key (ensure this is secure and not hardcoded in production)
openai.api_key = os.getenv('OPENAI_API_KEY')


facts_by_day = {}
current_date = None
auto_approve = False
stored_question = None

def main():
    global facts_by_day
    facts_by_day = load_facts()
    
    st.title('Call Log Processor')
    with st.sidebar:
        selected_screen = st.radio("Select Screen", ("Question and Answer", "Document Addition"))

    if selected_screen == "Question and Answer":
        question_and_answer_screen()
    else:
        document_addition_screen()

def question_and_answer_screen():
    global current_date, stored_question, facts_by_day

    # Display question and answer area
    st.header("Question and Answers")
    if stored_question:
        st.write("Question:", stored_question)
    else:
        st.write("No question has been set yet.")

    # Display time navigation slider
    if current_date is None and facts_by_day:
        current_date = min(facts_by_day.keys())
    elif not facts_by_day:
        st.write("No documents added yet.")
        return

    min_date = min(facts_by_day.keys())
    max_date = max(facts_by_day.keys())

    # Convert date strings to datetime objects
    min_date = datetime.strptime(min_date, "%Y-%m-%d")
    max_date = datetime.strptime(max_date, "%Y-%m-%d")
    
    # Ensure that min_date is strictly less than max_date
    if min_date >= max_date:
        st.write("Error: min_date is equal to or greater than max_date.")
        return

    current_date = datetime.strptime(current_date, "%Y-%m-%d")

    # selected_date = st.slider("Select Date", min_value=min_date, max_value=max_date, value=current_date)
    selected_date = st.slider("Select Date", min_value=min_date, max_value=max_date, value=current_date)

    # Convert selected_date back to string format
    current_date = selected_date.strftime("%Y-%m-%d")

    if current_date in facts_by_day:
        for entry in facts_by_day[current_date]:
            # Assuming each entry now includes both a 'question' and 'fact'
            st.write("Question:", entry["question"])
            st.write("Answer:", entry["fact"])
    else:
        st.write("No facts found for this date.")
    
def document_addition_screen():
    global facts_by_day, auto_approve, stored_question

    st.header("Add Documents")

    # Get document URLs and question from user
    question = st.text_input("Enter your question:")
    document_urls = st.text_area("Enter document URLs (one per line):")
    auto_approve = st.checkbox("Auto-approve suggestions")
    
    stored_question = question

    # Process documents when the user clicks the submit button
    if st.button("Submit"):
        print('=====================================')
        for url in document_urls.strip().split("\n"):
            print(url)
            process_document(question, url)
        # Display updated facts
        st.write("Facts updated:")
        submitted_date = extract_date_from_url(document_urls.split("\n")[0])  # Assuming single URL submission for simplicity
        if submitted_date:
            display_facts_for_date(facts_by_day, submitted_date)
        else:
            st.write("Invalid URL or date format.")

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


def fetch_content_from_url(url: str):
    """
    Fetches and parses the call log content from the given URL.
    
    Args:
        url (str): The URL of the call log file.
        
    Returns:
        list of dicts: A list where each dict contains 'speaker' and 'dialogue'.
    """
    response = requests.get(url)
    response.raise_for_status()  # This will raise an exception for 4XX/5XX errors
    lines = response.text.split('\n')
    parsed_content = []
    
    for i, line in enumerate(lines):
        if '-->' in line:  # This identifies the timestamp lines and skips them
            continue
        parts = line.split(': ', 1)  # Splitting on ': ' to separate the speaker from the dialogue
        if len(parts) == 2:
            parsed_content.append({'speaker': parts[0], 'dialogue': parts[1]})
    return parsed_content
    
    
def extract_facts(question_response, document_responses):
    # Extract facts based on the responses
    facts_by_day = {}

    # Iterate over document_responses and use the corresponding question_response
    for url, document_response in document_responses.items():
        date = parse_date(urlparse(url).path.split('_')[2]).strftime("%Y-%m-%d")
        if date not in facts_by_day:
            facts_by_day[date] = []

        # Use the full question_response for each document
        response = question_response  # Corrected line

        # Split the response into individual facts (assuming they are numbered)
        facts = [fact.strip() for fact in response.split('\n') if fact.strip()]

        # Extract the actual fact text, handling cases without ". " separator
        extracted_facts = []
        for fact in facts:
            parts = fact.split('. ', 1)  # Split at most once
            if len(parts) == 2:  # If ". " separator is present
                extracted_facts.append(parts[1])  # Extract the fact text
            else:
                extracted_facts.append(fact)  # Otherwise, use the entire fact string
        facts_by_day[date].extend(extracted_facts)  # Add the extracted facts to the list
        print(facts_by_day)
    return facts_by_day

def process_document(question, url):
    global facts_by_day
    document_content = fetch_content_from_url(url)
    if document_content:
        date = parse_date(urlparse(url).path.split('_')[2]).strftime("%Y-%m-%d")
        response = generate_response(question, document_content)
        suggested_facts = extract_facts(response, {url: document_content})
        
        if date not in facts_by_day:
            facts_by_day[date] = []
            unique_facts_set = set()  # Initialize a set to track unique facts
        else:
            # Initialize the set with existing facts for the date to preserve uniqueness
            unique_facts_set = set(json.dumps(fact) for fact in facts_by_day[date])
        
        for fact in suggested_facts[date]:  # Access facts for the specific date
            fact_entry = {"question": stored_question, "fact": fact}
            fact_str = json.dumps(fact_entry)  # Convert the dictionary to a string
            if fact_str not in unique_facts_set:  # Check for uniqueness
                unique_facts_set.add(fact_str)  # Mark as seen
                facts_by_day[date].append(fact_entry)  # Append the original dict
                save_facts(facts_by_day)  # Save after appending


def save_facts(facts_by_day, filename="facts.json"):
    with open(filename, "w") as f:
        json.dump(facts_by_day, f)


import json

def load_facts(filename="facts.json"):
    try:
        with open(filename, "r") as f:
            loaded_facts = json.load(f)
            cleaned_facts = {}

            for date, facts_list in loaded_facts.items():
                seen = set()  # A set to track seen (question, fact) tuples
                unique_facts = []
                for fact_dict in facts_list:
                    # Assuming each fact_dict is {"question": "...", "fact": "..."}
                    identifier = (fact_dict["question"], fact_dict["fact"])
                    if identifier not in seen:
                        seen.add(identifier)
                        unique_facts.append(fact_dict)
                
                cleaned_facts[date] = unique_facts

            return cleaned_facts
    except FileNotFoundError:
        return {}  # Return an empty dictionary if the file doesn't exist
    except JSONDecodeError:
        return {}  # Return an empty dictionary if the file is empty or malformatted

def display_facts(facts_by_day):
    # Display facts in the main area of the app
    for day, entries in facts_by_day.items():
        st.write(f"Date: {day}")
        for entry in entries:
            # Assuming each entry is a dictionary with 'question' and 'fact' keys
            question = entry.get("question", "No question provided")
            fact = entry.get("fact", "No fact provided")
            # st.write(f"Question: {question}")
            st.write(f"{fact}")

def display_facts_for_date(facts_by_day, date):
    # Display facts for a specific date with duplicate removal
    if date in facts_by_day:
        st.write(f"Date: {date}")
        seen_facts = set()  # Use a set to track unique question-fact combinations
        
        for entry in facts_by_day[date]:
            # Create a unique identifier for each question-fact pair
            identifier = (entry.get("question", ""), entry.get("fact", ""))
            if identifier not in seen_facts:
                seen_facts.add(identifier)  # Mark this question-fact pair as seen
                # Now display the question and fact
                question = entry.get("question", "No question provided")
                fact = entry.get("fact", "No fact provided")
                st.write(f"{fact}")
    else:
        st.write(f"No facts found for date: {date}")


def extract_date_from_url(url):
    # Extract and return the date part as "YYYY-MM-DD"
    parts = url.split('_')
    if len(parts) >= 3:
        date_str = parts[2]
        return datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")
    else:
        return None

if __name__ == '__main__':
    main()
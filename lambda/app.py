import os
import sys 
import json

if "LAMBDA_TASK_ROOT" in os.environ:
    envLambdaTaskRoot = os.environ["LAMBDA_TASK_ROOT"]
    sys.path.insert(0, "/var/lang/lib/python3.9/site-packages")

from langchain.retrievers import AmazonKendraRetriever
from langchain.chains import ConversationalRetrievalChain
from langchain.llms.bedrock import Bedrock
from langchain.prompts import PromptTemplate

retriever = AmazonKendraRetriever(
    index_id=os.environ['kendra_index_id'],
    region_name=os.environ['aws_region']
)

llm_jurassic_ultra = Bedrock(
    model_id="ai21.j2-ultra-v1",
    endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com",
    model_kwargs={"temperature": 0.7, "maxTokens": 500, "numResults": 1}
)

llm_jurassic_mid = Bedrock(
    model_id="ai21.j2-mid-v1",
    endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com",
    model_kwargs={"temperature": 0.7, "maxTokens": 300, "numResults": 1}
)

#Create template for combining chat history and follow up question into a standalone question.
question_generator_chain_template = """
Here is some chat history contained in the <chat_history> tags and a follow-up question in the <follow_up> tags:

<chat_history>
{chat_history}
</chat_history>

<follow_up>
{question}
</follow_up>

Combine the chat history and follow up question into a standalone question.
"""

question_generator_chain_prompt = PromptTemplate.from_template(question_generator_chain_template)

#Create template for asking the question of the given context.
combine_docs_chain_template = """
You are a friendly, concise chatbot. Here is some context, contained in <context> tags:

<context>
{context}
</context>

Given the context answer this question: {question}
"""
combine_docs_chain_prompt = PromptTemplate.from_template(combine_docs_chain_template)

# RetrievalQA instance with custom prompt template
qa = ConversationalRetrievalChain.from_llm(
    llm=llm_jurassic_ultra,
    condense_question_llm=llm_jurassic_mid,
    retriever=retriever,
    return_source_documents=True,
    condense_question_prompt=question_generator_chain_prompt,
    combine_docs_chain_kwargs={"prompt": combine_docs_chain_prompt}
)

# This function handles formatting responses back to Lex.
def lex_format_response(event, response_text, chat_history):
    event['sessionState']['intent']['state'] = "Fulfilled"

    return {
        'sessionState': {
            'sessionAttributes': {'chat_history': chat_history},
            'dialogAction': {
                'type': 'Close'
            },
            'intent': event['sessionState']['intent']
        },
        'messages': [{'contentType': 'PlainText','content': response_text}],
        'sessionId': event['sessionId'],
        'requestAttributes': event['requestAttributes'] if 'requestAttributes' in event else None
    }

def lambda_handler(event, context):
    if(event['inputTranscript']):
        user_input = event['inputTranscript']
        prev_session = event['sessionState']['sessionAttributes']

        print(prev_session)

        # Load chat history from previous session.
        if 'chat_history' in prev_session:
            chat_history = list(tuple(pair) for pair in json.loads(prev_session['chat_history']))
        else:
            chat_history = []

        if user_input.strip() == "":
            result = {"answer": "Please provide a question."}
        else:
            input_variables = {
                "question": user_input,
                "chat_history": chat_history
            }

            print(f"Input variables: {input_variables}")

            result = qa(input_variables)

        # If Kendra doesn't return any relevant documents, then hard code the response 
        # as an added protection from hallucinations.
        if(len(result['source_documents']) > 0):
            response_text = result["answer"].strip() 
        else:
            response_text = "I don't know"

        # Append user input and response to chat history. Then only retain last 3 message histories.
        chat_history.append((f"Human: {user_input}", f"Assistant: {response_text}"))
        chat_history = chat_history[-3:]

        return lex_format_response(event, response_text, json.dumps(chat_history))

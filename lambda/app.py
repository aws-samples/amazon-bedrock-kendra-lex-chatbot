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

REGION_NAME = os.environ['aws_region']

MODEL_TYPE = "CLAUDE"

retriever = AmazonKendraRetriever(
    index_id=os.environ['kendra_index_id'],
    region_name=REGION_NAME
)

if(MODEL_TYPE == "CLAUDE"):
    llm = Bedrock(
        model_id="anthropic.claude-v2:1",
        endpoint_url="https://bedrock-runtime." + REGION_NAME + ".amazonaws.com",
        model_kwargs={"temperature": 0.7, "max_tokens_to_sample": 500}
    )

    condense_question_llm = Bedrock(
        model_id="anthropic.claude-instant-v1",
        endpoint_url="https://bedrock-runtime." + REGION_NAME + ".amazonaws.com",
        model_kwargs={"temperature": 0.7, "max_tokens_to_sample": 300}
    )
else:
    llm = Bedrock(
        model_id="ai21.j2-ultra-v1",
        endpoint_url="https://bedrock-runtime." + REGION_NAME + ".amazonaws.com",
        model_kwargs={"temperature": 0.7, "maxTokens": 500, "numResults": 1}
    )

    condense_question_llm = Bedrock(
        model_id="ai21.j2-mid-v1",
        endpoint_url="https://bedrock-runtime." + REGION_NAME + ".amazonaws.com",
        model_kwargs={"temperature": 0.7, "maxTokens": 300, "numResults": 1}
    )

#Create template for combining chat history and follow up question into a standalone question.
question_generator_chain_template = """
Human: Here is some chat history contained in the <chat_history> tags. If relevant, add context from the Human's previous questions to the new question. Return only the question. No preamble. If unsure, ask the Human to clarify. Think step by step.

Assistant: Ok

<chat_history>
{chat_history}

Human: {question}
</chat_history>

Assistant:
"""

question_generator_chain_prompt = PromptTemplate.from_template(question_generator_chain_template)

#Create template for asking the question of the given context.
combine_docs_chain_template = """
Human: You are a friendly, concise chatbot. Here is some context, contained in <context> tags. Answer this question as concisely as possible with no tags. Say I don't know if the answer isn't given in the context: {question}

<context>
{context}
</context>

Assistant:
"""
combine_docs_chain_prompt = PromptTemplate.from_template(combine_docs_chain_template)

# RetrievalQA instance with custom prompt template
qa = ConversationalRetrievalChain.from_llm(
    llm=llm,
    condense_question_llm=condense_question_llm,
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
        # It seemed to work better with AI responses removed, but try adding them back in. {response_text}
        chat_history.append((f"{user_input}", f"..."))
        chat_history = chat_history[-3:]

        return lex_format_response(event, response_text, json.dumps(chat_history))

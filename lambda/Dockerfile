FROM public.ecr.aws/lambda/python:3.9

# Copy requirements.txt
COPY lambda/requirements.txt ${LAMBDA_TASK_ROOT}

# Copy function code
COPY lambda/app.py ${LAMBDA_TASK_ROOT}

# Install the specified packages
#RUN pip install -r requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD [ "app.lambda_handler" ]
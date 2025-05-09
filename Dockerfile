FROM python:3.10

WORKDIR /app

# Install pipenv
RUN pip install pipenv

# Copy Pipfile and Pipfile.lock
COPY Pipfile Pipfile.lock ./

# Install dependencies
RUN pipenv install --system --deploy

# Copy the rest of the application
COPY . .

# Port
EXPOSE 10000

# Command to run the application
CMD ["python", "manage.py", "runserver"]
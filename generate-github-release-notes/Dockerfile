FROM python:3.13-slim

RUN pip install --no-cache-dir PyGithub

COPY generate-github-release-notes.py /usr/local/bin/generate-github-release-notes.py

ENTRYPOINT ["python3", "/usr/local/bin/generate-github-release-notes.py"]

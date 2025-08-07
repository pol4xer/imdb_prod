pip install -U pip
pip install -U poetry
if [ -f poetry.lock ]; then
    rm poetry.lock
fi
poetry install
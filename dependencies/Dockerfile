FROM harbor.testbed.spice-platform.eu/partner/iisas/domino/domino-base-piece:latest

COPY config.toml domino/pieces_repository/
COPY pieces domino/pieces_repository/pieces
COPY catalog domino/pieces_repository/catalog
COPY .domino domino/pieces_repository/.domino

COPY dependencies/requirements.txt domino/pieces_repository/dependencies/

RUN apt update && apt -y install git && apt clean

RUN pip install --no-cache-dir -r domino/pieces_repository/dependencies/requirements.txt

ENV PYTHONPATH="/home/domino/pieces_repository:${PYTHONPATH}"

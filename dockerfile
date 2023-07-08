ARG FUNCTION_DIRECTORY="/function"

FROM python:3.10-buster as build-image

ARG FUNCTION_DIRECTORY

RUN mkdir -p ${FUNCTION_DIRECTORY}

ARG FUNCTION_NAME

COPY requirements.txt ${FUNCTION_DIRECTORY}

COPY cmd/lambda/${FUNCTION_NAME}/main.py ${FUNCTION_DIRECTORY}

COPY pkg ${FUNCTION_DIRECTORY}/pkg

COPY lstm_model.h5 ${FUNCTION_DIRECTORY}/

WORKDIR ${FUNCTION_DIRECTORY}

RUN pip3 install --target ${FUNCTION_DIRECTORY} awslambdaric

RUN pip3 install --requirement requirements.txt --target ${FUNCTION_DIRECTORY}

FROM python:3.10-buster

ARG FUNCTION_DIRECTORY

COPY --from=build-image ${FUNCTION_DIRECTORY} ${FUNCTION_DIRECTORY}

ENV S3_DATA_BUCKET_NAME=""

ENV ALPACA_API_KEY=""

ENV ALPACA_API_SECRET=""

ENV ALPACA_ACCOUNT_ID=""

ENV FINNHUB_API_KEY=""

ENV ALPHA_VANTAGE_API_KEY=""

WORKDIR ${FUNCTION_DIRECTORY}

ENTRYPOINT [ "/usr/local/bin/python", "-m", "awslambdaric" ]

CMD [ "main.handler" ]

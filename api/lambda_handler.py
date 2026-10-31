# AWS Lambda's entry point for the API. Lambda hands the function
# an API Gateway event (a JSON description of the HTTP request), not a socket;
# Mangum turns it into a request for the same FastAPI app uvicorn serves
# locally, and the response back into what API Gateway expects.

from mangum import Mangum

from api.main import app

handler = Mangum(app)

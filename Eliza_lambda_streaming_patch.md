### **Subject: Specification for AWS Lambda OpenAI-Compatible Endpoint Update**

**1\. Overview**

This document outlines the required changes for our custom AWS Lambda function to ensure compatibility with LiteLLM's streaming chat completion feature.

**2\. Problem Description**

When LiteLLM sends a chat completion request with stream: true, our Lambda returns a standard, single JSON object. LiteLLM's streaming parser expects a response formatted as Server-Sent Events (SSE), causing it to receive no data and return a blank response to the end-user.

**3\. High-Level Requirement**

The Lambda function must be updated to detect streaming requests and format its response according to the OpenAI-compatible SSE protocol. If the request is non-streaming, the existing behavior should be maintained.

**4\. Technical Specifications**

**A. Detect Streaming vs. Non-Streaming Requests:**

* Parse the JSON body of the incoming POST request.  
* Check for the presence and value of the stream key.  
* If request\_body.get("stream") is True, follow the **Streaming Response** specifications.  
* Otherwise, follow the **Non-Streaming Response** specifications.

**B. Streaming Response ("stream": true):**

1. **HTTP Status Code:**  
   * 200 OK  
2. **HTTP Headers:**  
   * The response headers **must** include:  
     * Content-Type: text/event-stream; charset=utf-8  
     * Cache-Control: no-cache  
3. **HTTP Body:**  
   * The body must be a string composed of one or more data chunks, followed by a final termination chunk.  
   * Each chunk must be a string prefixed with data:  and followed by two newlines (\\n\\n).  
   * **Content Chunk:** The JSON payload for a content chunk must follow this structure:

{  
  "id": "chatcmpl-UNIQUE\_ID",  
  "object": "chat.completion.chunk",  
  "created": 1694268190, // Current Unix timestamp  
  "model": "eliza-lambda", // Your model name  
  "choices": \[  
    {  
      "index": 0,  
      "delta": { "content": "The response text." },  
      "finish\_reason": null  
    }  
  \]  
}

* **Termination Chunk:** After all content chunks are sent, the stream **must** be closed by sending a final chunk where the data payload is the literal string \[DONE\].

**Example Streaming Body (for a single response "Please go on."):**

data: {"id":"...","object":"chat.completion.chunk","created":...,"model":"eliza-lambda","choices":\[{"index":0,"delta":{"content":"Please go on."},"finish\_reason":null}\]}

data: \[DONE\]

**C. Non-Streaming Response ("stream": false or key not present):**

* No changes are required. Continue to return the standard, complete JSON object with a Content-Type of application/json.

**5\. Acceptance Criteria**

* When a request is sent to the Lambda with "stream": true, the response has a Content-Type of text/event-stream and the body is in the specified SSE format.  
* When a request is sent without "stream": true, the Lambda returns a standard application/json response as it does today.  
* The "Test Key" feature in the LiteLLM Web UI successfully displays the chat response from the updated Lambda.


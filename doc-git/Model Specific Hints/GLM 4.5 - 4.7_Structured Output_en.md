### Structured Output for GLM 4.5 - 4.7, GLM 5
## Quelle: https://docs.z.ai/guides/capabilities/struct-output

> ## Documentation Index
> Fetch the complete documentation index at: https://docs.z.ai/llms.txt
> Use this file to discover all available pages before exploring further.

# Thinking (Deep Thinking) & Structured Output

Powerful thinking behavior matters for local LM Studio .gguf usage of GLM 4.5 - 4.7:

> Benchmark note: the local suite now treats this as a provider/runtime policy, not just an LM Studio JSON tweak. For LM Studio the parsing block lives in the JSON config; other providers need an equivalent runtime/template translation.

* **Thinking mode** per model (Quelle: https://docs.z.ai/guides/capabilities/thinking):
  * GLM-4.7 and GLM-4.5V use **forced thinking** (always reason before answering).
  * GLM-4.6 / GLM-4.5 use **auto / hybrid thinking** (the model decides, `enable_thinking` toggles).
  
* **Response markers** in the GGUF chat templates are ` thinking` (start) and ` response` (end).

* In LM Studio the block `llm.prediction.reasoning.parsing` MUST be set to
  `{"enabled": true, "startString": " thinking", "endString": " response"}` 
  so the reasoning text is stripped from the final `content`. 
  
  With `enabled: false` the raw ` thinking…response` block leaks into the assistant message, 
  which breaks JSON mode (`response_format: json_object`) because the `content` is no longer valid JSON.
  
* `enabled: false` was previously injected into all GLM configs by the
  gpt-oss-20b-`patch_reasoning_effort.py` tool by mistake (fixed locally 2026-08-03).
  Working reference: `mradermacher` GLM-4.7-Flash-REAP i1 config keeps parsing enabled:true.

# Structured Output

**Structured output (JSON mode)** ensures that AI returns JSON data conforming to predefined formats, 
providing reliable guarantees for programmatic processing of AI outputs.

## Features

The **structured output** feature provides AI models with strict data format control capabilities, supporting various 
complex data structures and validation requirements.

### Core Parameters

* **`response_format`**: Specifies the response format, set to `{"type": "json_object"}` to enable JSON mode
* **`model`**: Use models that support structured output, such as `glm-5`, `glm-4.7`, `glm-4.5`, `glm-4.6`, etc.
* **`messages`**: Define the expected JSON structure and field requirements in system messages

## Code Examples

**Install SDK**

```bash theme={null}
# Install latest version
pip install zai-sdk

# Or specify version
pip install zai-sdk==0.2.3
```

**Verify Installation**

```python theme={null}
import zai
print(zai.__version__)
```

**Complete Example**

The following is a complete structured output example demonstrating how to perform sentiment analysis and return structured JSON results:

```python theme={null}
from zai import ZaiClient
import json

# Initialize client
client = ZaiClient(api_key="your-api-key")

# Basic JSON mode
response = client.chat.completions.create(
    model="glm-5",
    messages=[
        {
            "role": "system",
            "content": """
            You are a sentiment analysis expert. Please return analysis results in the following JSON format:
            {
                "sentiment": "positive/negative/neutral",
                "confidence": 0.95,
                "emotions": ["joy", "excitement"],
                "keywords": ["weather", "mood"],
                "analysis": "Detailed analysis explanation"
            }
            """
        },
        {
            "role": "user",
            "content": "Please analyze the sentiment of this sentence: 'The weather is really nice today, I'm feeling very happy!'"
        }
    ],
    response_format={
        "type": "json_object"
    }
)

# Parse results
result = json.loads(response.choices[0].message.content)
print(f"Sentiment: {result['sentiment']}")
print(f"Confidence: {result['confidence']}")
print(f"Emotions: {result['emotions']}")
```

## Basic Usage

<Tabs>
  <Tab title="Simple JSON Output">
    **Simple JSON Output**

    ```python theme={null}
    from zai import ZaiClient

    client = ZaiClient(api_key="your-api-key")

    # Basic JSON mode
    response = client.chat.completions.create(
        model="glm-5",
        messages=[
            {
                "role": "user",
                "content": "Please analyze the sentiment of this sentence: 'The weather is really nice today, I'm feeling very happy!'"
            }
        ],
        response_format={
            "type": "json_object"
        }
    )

    import json
    result = json.loads(response.choices[0].message.content)
    print(result)
    ```
  </Tab>

  <Tab title="Specify JSON Structure">
    ### Specify JSON Structure

    ```python theme={null}
    # Specify specific JSON structure
    response = client.chat.completions.create(
        model="glm-5",
        messages=[
            {
                "role": "system",
                "content": """
                You are a sentiment analysis expert. Please return analysis results in the following JSON format:
                {
                    "sentiment": "positive/negative/neutral",
                    "confidence": 0.95,
                    "emotions": ["joy", "excitement"],
                    "keywords": ["weather", "mood"],
                    "analysis": "Detailed analysis explanation"
                }
                """
            },
            {
                "role": "user",
                "content": "Please analyze the sentiment of this sentence: 'The weather is really nice today, I'm feeling very happy!'"
            }
        ],
        response_format={
            "type": "json_object"
        }
    )

    result = json.loads(response.choices[0].message.content)
    print(f"Sentiment: {result['sentiment']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Emotions: {result['emotions']}")
    ```
  </Tab>

  <Tab title="Schema Validation">
    ### Using JSON Schema Validation

    ```python theme={null}
    import jsonschema
    from jsonschema import validate

    # Define JSON Schema
    schema = {
        "type": "object",
        "properties": {
            "sentiment": {
                "type": "string",
                "enum": ["positive", "negative", "neutral"]
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1
            },
            "emotions": {
                "type": "array",
                "items": {"type": "string"}
            },
            "keywords": {
                "type": "array",
                "items": {"type": "string"}
            },
            "analysis": {
                "type": "string"
            }
        },
        "required": ["sentiment", "confidence", "analysis"]
    }

    def analyze_sentiment_with_validation(text):
        """Sentiment analysis with validation"""
        response = client.chat.completions.create(
            model="glm-5",
            messages=[
                {
                    "role": "system",
                    "content": f"""
                    Please return sentiment analysis results according to the following JSON Schema format:
                    {json.dumps(schema, indent=2, ensure_ascii=False)}
                    """
                },
                {
                    "role": "user",
                    "content": f"Please analyze the sentiment of this sentence: '{text}'"
                }
            ],
            response_format={"type": "json_object"}
        )
        
        try:
            result = json.loads(response.choices[0].message.content)
            # Validate JSON structure
            validate(instance=result, schema=schema)
            return result
        except jsonschema.exceptions.ValidationError as e:
            print(f"JSON validation failed: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"JSON parsing failed: {e}")
            return None

    # Usage example
    result = analyze_sentiment_with_validation("The weather is really nice today, I'm feeling very happy!")
    if result:
        print("Analysis result:", result)
    ```
  </Tab>
</Tabs>

## Scenario Examples

<Warning>
  When using JSON mode for data extraction, please ensure the quality and format of input data to achieve the best extraction results.
</Warning>

<Accordion title="Data Extraction and Structuring Complete Implementation">
  ```python theme={null}
  class DataExtractor:
      def __init__(self, api_key):
          self.client = ZaiClient(api_key=api_key)
      
      def extract_contact_info(self, text):
          """Extract contact information"""
          schema = {
              "type": "object",
              "properties": {
                  "contacts": {
                      "type": "array",
                      "items": {
                          "type": "object",
                          "properties": {
                              "name": {"type": "string"},
                              "phone": {"type": "string"},
                              "email": {"type": "string"},
                              "company": {"type": "string"},
                              "position": {"type": "string"},
                              "address": {"type": "string"}
                          },
                          "required": ["name"]
                      }
                  },
                  "total_count": {"type": "integer"},
                  "extraction_confidence": {"type": "number"}
              },
              "required": ["contacts", "total_count"]
          }
          
          response = self.client.chat.completions.create(
              model="glm-5",
              messages=[
                  {
                      "role": "system",
                      "content": f"""
                      You are an information extraction expert. Please extract all contact information from the text,
                      return in the following JSON format:
                      {json.dumps(schema, indent=2, ensure_ascii=False)}
                      
                      Note:
                      - If a field has no information, do not include that field
                      - phone field should be in standardized phone number format
                      - email field should be a valid email address
                      - extraction_confidence represents overall extraction confidence (0-1)
                      """
                  },
                  {
                      "role": "user",
                      "content": f"Please extract contact information from the following text:\n\n{text}"
                  }
              ],
              response_format={"type": "json_object"}
          )
          
          try:
              result = json.loads(response.choices[0].message.content)["properties"]
              validate(instance=result, schema=schema)
              return result
          except Exception as e:
              print(f"Extraction failed: {e}")
              return None
      
      def extract_product_info(self, product_description):
          """Extract product information"""
          schema = {
              "type": "object",
              "properties": {
                  "product_name": {"type": "string"},
                  "brand": {"type": "string"},
                  "category": {"type": "string"},
                  "price": {
                      "type": "object",
                      "properties": {
                          "amount": {"type": "number"},
                          "currency": {"type": "string"},
                          "original_price": {"type": "number"},
                          "discount": {"type": "number"}
                      }
                  },
                  "specifications": {
                      "type": "object",
                      "additionalProperties": True
                  },
                  "features": {
                      "type": "array",
                      "items": {"type": "string"}
                  },
                  "availability": {
                      "type": "object",
                      "properties": {
                          "in_stock": {"type": "boolean"},
                          "quantity": {"type": "integer"},
                          "shipping_time": {"type": "string"}
                      }
                  },
                  "ratings": {
                      "type": "object",
                      "properties": {
                          "average_rating": {"type": "number"},
                          "total_reviews": {"type": "integer"}
                      }
                  }
              },
              "required": ["product_name"]
          }
          
          response = self.client.chat.completions.create(
              model="glm-5",
              messages=[
                  {
                      "role": "system",
                      "content": f"""
                      Please extract structured information from product description, return in the following format:
                      {json.dumps(schema, indent=2, ensure_ascii=False)}
                      
                      Note:
                      - Price information should accurately extract values and currency units
                      - specifications should include all technical specifications
                      - features should list main functional features
                      - Do not guess if information is unclear
                      """
                  },
                  {
                      "role": "user",
                      "content": f"Product description:\n{product_description}"
                  }
              ],
              response_format={"type": "json_object"}
          )
          
          try:
              result = json.loads(response.choices[0].message.content)
              validate(instance=result, schema=schema)
              return result
          except Exception as e:
              print(f"Product information extraction failed: {e}")
              return None
      
      def extract_event_info(self, event_text):
          """Extract event information"""
          schema = {
              "type": "object",
              "properties": {
                  "events": {
                      "type": "array",
                      "items": {
                          "type": "object",
                          "properties": {
                              "title": {"type": "string"},
                              "description": {"type": "string"},
                              "start_time": {"type": "string"},
                              "end_time": {"type": "string"},
                              "location": {"type": "string"},
                              "organizer": {"type": "string"},
                              "participants": {
                                  "type": "array",
                                  "items": {"type": "string"}
                              },
                              "category": {"type": "string"},
                              "priority": {
                                  "type": "string",
                                  "enum": ["high", "medium", "low"]
                              },
                              "status": {
                                  "type": "string",
                                  "enum": ["scheduled", "ongoing", "completed", "cancelled"]
                              }
                          },
                          "required": ["title", "start_time"]
                      }
                  }
              },
              "required": ["events"]
          }
          
          response = self.client.chat.completions.create(
              model="glm-5",
              messages=[
                  {
                      "role": "system",
                      "content": f"""
                      Please extract all event information from the text, return in the following format:
                      {json.dumps(schema, indent=2, ensure_ascii=False)}
                      
                      Time format requirements:
                      - Use ISO 8601 format: YYYY-MM-DDTHH:MM:SS
                      - If only date available, use: YYYY-MM-DD
                      - If time is unclear, try to infer reasonable time
                      """
                  },
                  {
                      "role": "user",
                      "content": f"Please extract event information from the following text:\n\n{event_text}"
                  }
              ],
              response_format={"type": "json_object"}
          )
          
          try:
              result = json.loads(response.choices[0].message.content)
              validate(instance=result, schema=schema)
              return result
          except Exception as e:
              print(f"Event information extraction failed: {e}")
              return None

  # Usage example
  extractor = DataExtractor("your_api_key")

  # Extract contact information
  contact_text = """
  Zhang San, mobile: 13800138000, email: zhangsan@example.com,
  works as Technical Director at Beijing Technology Co., Ltd.
  Company address: No. 123, Technology Park, Chaoyang District, Beijing.

  Li Si, phone: 010-12345678, work email: lisi@company.com,
  is a Product Manager at Shanghai Innovation Company.
  """

  contacts = extractor.extract_contact_info(contact_text)
  if contacts:
      print(f"Extracted {contacts['total_count']} contacts")
      for contact in contacts['contacts']:
          print(f"Name: {contact['name']}")
          if 'phone' in contact:
              print(f"Phone: {contact['phone']}")
  ```
</Accordion>

<Accordion title="API Response Formatting Complete Implementation">
  ```python theme={null}
  class APIResponseFormatter:
      def __init__(self, api_key):
          self.client = ZaiClient(api_key=api_key)
      
      def format_search_results(self, query, raw_results):
          """Format search results"""
          schema = {
              "type": "object",
              "properties": {
                  "query": {"type": "string"},
                  "total_results": {"type": "integer"},
                  "results": {
                      "type": "array",
                      "items": {
                          "type": "object",
                          "properties": {
                              "title": {"type": "string"},
                              "url": {"type": "string"},
                              "snippet": {"type": "string"},
                              "relevance_score": {"type": "number"},
                              "source_type": {"type": "string"},
                              "publish_date": {"type": "string"},
                              "tags": {
                                  "type": "array",
                                  "items": {"type": "string"}
                              }
                          },
                          "required": ["title", "url", "snippet"]
                      }
                  },
                  "suggestions": {
                      "type": "array",
                      "items": {"type": "string"}
                  },
                  "filters": {
                      "type": "object",
                      "properties": {
                          "date_range": {"type": "string"},
                          "source_types": {
                              "type": "array",
                              "items": {"type": "string"}
                          },
                          "languages": {
                              "type": "array",
                              "items": {"type": "string"}
                          }
                      }
                  }
              },
              "required": ["query", "total_results", "results"]
          }
          
          response = self.client.chat.completions.create(
              model="glm-5",
              messages=[
                  {
                      "role": "system",
                      "content": f"""
                      Please format search results into standard JSON format:
                      {json.dumps(schema, indent=2, ensure_ascii=False)}
                      
                      Requirements:
                      - Calculate relevance score for each result (0-1)
                      - Identify content type (article, video, image, document, etc.)
                      - Extract publish date (if available)
                      - Generate relevant tags
                      - Provide search suggestions
                      """
                  },
                  {
                      "role": "user",
                      "content": f"Query: {query}\n\nRaw results:\n{raw_results}"
                  }
              ],
              response_format={"type": "json_object"}
          )
          
          try:
              result = json.loads(response.choices[0].message.content)
              validate(instance=result, schema=schema)
              return result
          except Exception as e:
              print(f"Formatting failed: {e}")
              return None
      
      def format_analytics_data(self, raw_data, metrics):
          """Format analytics data"""
          schema = {
              "type": "object",
              "properties": {
                  "summary": {
                      "type": "object",
                      "properties": {
                          "total_records": {"type": "integer"},
                          "date_range": {
                              "type": "object",
                              "properties": {
                                  "start_date": {"type": "string"},
                                  "end_date": {"type": "string"}
                              }
                          },
                          "key_insights": {
                              "type": "array",
                              "items": {"type": "string"}
                          }
                      }
                  },
                  "metrics": {
                      "type": "object",
                      "additionalProperties": {
                          "type": "object",
                          "properties": {
                              "current_value": {"type": "number"},
                              "previous_value": {"type": "number"},
                              "change_percentage": {"type": "number"},
                              "trend": {
                                  "type": "string",
                                  "enum": ["up", "down", "stable"]
                              },
                              "unit": {"type": "string"}
                          }
                      }
                  },
                  "time_series": {
                      "type": "array",
                      "items": {
                          "type": "object",
                          "properties": {
                              "timestamp": {"type": "string"},
                              "values": {
                                  "type": "object",
                                  "additionalProperties": {"type": "number"}
                              }
                          }
                      }
                  },
                  "segments": {
                      "type": "array",
                      "items": {
                          "type": "object",
                          "properties": {
                              "name": {"type": "string"},
                              "value": {"type": "number"},
                              "percentage": {"type": "number"},
                              "color": {"type": "string"}
                          }
                      }
                  }
              },
              "required": ["summary", "metrics"]
          }
          
          response = self.client.chat.completions.create(
              model="glm-5",
              messages=[
                  {
                      "role": "system",
                      "content": f"""
                      Please format analytics data into standard format:
                      {json.dumps(schema, indent=2, ensure_ascii=False)}
                      
                      Focus indicators:{', '.join(metrics)}
                      
                      Requirements:
                      - Calculate change percentage and trend
                      - Provide key insights
                      - Time series data sorted by time
                      - Segments data contain percentage
                      """
                  },
                  {
                      "role": "user",
                      "content": f"Raw data: \n{raw_data}"
                  }
              ],
              response_format={"type": "json_object"}
          )
          
          try:
              result = json.loads(response.choices[0].message.content)
              validate(instance=result, schema=schema)
              return result
          except Exception as e:
              print(f"Analytics data formatting failed: {e}")
              return None

  # Usage example
  formatter = APIResponseFormatter("your_api_key")

  # Format search results
  raw_search = """
  1. Python Programming Tutorial - https://example.com/python-tutorial
     Detailed introduction to Python basic syntax and programming concepts...

  2. Python Data Analysis Practice - https://example.com/python-data
     Using pandas and numpy for data processing...
  """

  formatted_results = formatter.format_search_results("Python Tutorial", raw_search)
  if formatted_results:
      print(f"Found {formatted_results['total_results']} results")
      for result in formatted_results['results']:
          print(f"Title: {result['title']}")
          print(f"Relevance: {result['relevance_score']}")
  ```
</Accordion>

<Accordion title="Configuration Management and Validation Complete Implementation">
  ```python theme={null}
  class ConfigurationManager:
      def __init__(self, api_key):
          self.client = ZaiClient(api_key=api_key)

      def parse_config_file(self, config_text, config_type="general"):
          """Parse configuration file"""
          schemas = {
              "database": {
                  "type": "object",
                  "properties": {
                      "connections": {
                          "type": "array",
                          "items": {
                              "type": "object",
                              "properties": {
                                  "name": {"type": "string"},
                                  "host": {"type": "string"},
                                  "port": {"type": "integer"},
                                  "database": {"type": "string"},
                                  "username": {"type": "string"},
                                  "ssl": {"type": "boolean"},
                                  "pool_size": {"type": "integer"}
                              },
                              "required": ["name", "host", "database"]
                          }
                      },
                      "settings": {
                          "type": "object",
                          "properties": {
                              "timeout": {"type": "integer"},
                              "retry_attempts": {"type": "integer"},
                              "log_level": {
                                  "type": "string",
                                  "enum": ["DEBUG", "INFO", "WARNING", "ERROR"]
                              }
                          }
                      }
                  },
                  "required": ["connections"]
              },
              "api": {
                  "type": "object",
                  "properties": {
                      "endpoints": {
                          "type": "array",
                          "items": {
                              "type": "object",
                              "properties": {
                                  "name": {"type": "string"},
                                  "url": {"type": "string"},
                                  "method": {
                                      "type": "string",
                                      "enum": ["GET", "POST", "PUT", "DELETE"]
                                  },
                                  "headers": {"type": "object"},
                                  "timeout": {"type": "integer"},
                                  "rate_limit": {"type": "integer"}
                              },
                              "required": ["name", "url", "method"]
                          }
                      },
                      "authentication": {
                          "type": "object",
                          "properties": {
                              "type": {
                                  "type": "string",
                                  "enum": ["bearer", "basic", "api_key"]
                              },
                              "credentials": {"type": "object"}
                          }
                      }
                  },
                  "required": ["endpoints"]
              }
          }
          
          schema = schemas.get(config_type, {
              "type": "object",
              "additionalProperties": True
          })
          
          response = self.client.chat.completions.create(
              model="glm-5",
              messages=[
                  {
                      "role": "system",
                      "content": f"""
                      Please parse the configuration file and convert to JSON format:
                      {json.dumps(schema, indent=2, ensure_ascii=False)}
                      
                      Configuration type: {config_type}
                      
                      Requirements:
                      - Identify configuration items and values
                      - Convert data types (string, number, boolean)
                      - Handle arrays and nested objects
                      - Validate required fields
                      - Provide default values (if applicable)
                      """
                  },
                  {
                      "role": "user",
                      "content": f"Configuration file content:\n{config_text}"
                  }
              ],
              response_format={"type": "json_object"}
          )
          
          try:
              result = json.loads(response.choices[0].message.content)
              validate(instance=result, schema=schema)
              return result
          except Exception as e:
              print(f"Configuration parsing failed: {e}")
              return None
      
      def validate_configuration(self, config_data, validation_rules):
          """Validate configuration"""
          response = self.client.chat.completions.create(
              model="glm-5",
              messages=[
                  {
                      "role": "system",
                      "content": f"""
                      Please validate configuration data and return validation results:
                      
                      Return format:
                      {{
                          "is_valid": true/false,
                          "errors": [
                              {{
                                  "field": "field_name",
                                  "error": "error_description",
                                  "severity": "error/warning/info"
                              }}
                          ],
                          "warnings": [
                              {{
                                  "field": "field_name",
                                  "message": "warning_message"
                              }}
                          ],
                          "suggestions": [
                              "improvement_suggestion_1",
                              "improvement_suggestion_2"
                          ]
                      }}
                      
                      Validation rules: {validation_rules}
                      """
                  },
                  {
                      "role": "user",
                      "content": f"Configuration data:\n{json.dumps(config_data, indent=2, ensure_ascii=False)}"
                  }
              ],
              response_format={"type": "json_object"}
          )
          
          try:
              result = json.loads(response.choices[0].message.content)
              return result
          except Exception as e:
              print(f"Configuration validation failed: {e}")
              return None

  # Usage example
  config_manager = ConfigurationManager("your_api_key")

  # Parse database configuration
  db_config_text = """
  [database]
  host = localhost
  port = 5432
  database = myapp
  username = admin
  ssl = true
  pool_size = 10

  [settings]
  timeout = 30
  retry_attempts = 3
  log_level = INFO
  """

  config = config_manager.parse_config_file(db_config_text, "database")
  if config:
      print("Parsed configuration:", json.dumps(config, indent=2, ensure_ascii=False))
      
      # Validate configuration
      validation_rules = [
          "Port number must be in range 1-65535",
          "Database name cannot be empty",
          "Connection pool size should be greater than 0",
          "Timeout should be reasonable (1-300 seconds)"
      ]
      
      validation_result = config_manager.validate_configuration(config, validation_rules)
      if validation_result:
          print(f"Configuration validity: {validation_result['is_valid']}")
          if validation_result['errors']:
              print("Errors:", validation_result['errors'])
          if validation_result['warnings']:
              print("Warnings:", validation_result['warnings'])
  ```
</Accordion>

## Best Practices

<CardGroup cols={2}>
  <Card title="Schema Design Principles" icon="code">
    * Clarity: Field names and types should be clear and explicit
    * Completeness: Include all necessary validation rules
    * Flexibility: Consider future expansion needs
  </Card>

  <Card title="Error Handling Strategy" icon="shield-check">
    * Multi-layer validation: Schema validation + business logic validation
    * Fallback plan: Prepare simplified backup Schema
    * Logging: Record detailed error information
  </Card>
</CardGroup>

<Warning>
  JSON mode requires AI to strictly output according to specified format, but in some complex scenarios it may affect the naturalness of responses. It's recommended to find a balance between functionality and user experience.
</Warning>

<Tip>
  When designing JSON Schema, it's recommended to start with simple structures and gradually increase complexity. Also, providing detailed descriptions and examples for key fields helps AI better understand and generate JSON data that meets requirements.
</Tip>

## Local benchmark policy (2026-09-21)

The local LM Studio tests established two separate GLM families. GLM-4.7
Flash and GLM-4.7 Flash REAP are DeepSeek2-based (`architecture_family:
deepseek2`), whereas GLM-4.6V is a separate `glm4` vision architecture. The
two families must not inherit the same untested runner exception.

For GLM-4.7 Flash/REAP the benchmark blueprint is
`glm_reasoning_coding` and defines these API-side conditions:

- structured output is enabled per request with the OpenAI-compatible
  `response_format`; it is not enabled by adding a global GUI field;
- the response is requested without streaming because a streamed LM Studio
  response can deliver `reasoning_content` but lose the final `content` delta;
- the generic code-only/thinking suffix is omitted; the native template
  already separates the thinking and response channels;
- the benchmark `max_tokens` budget is 8192 for the complete response, while
  the LM Studio reasoning budget is synchronized to 4096. The two budgets
  must remain distinct so a long thinking trace does not consume the final
  code response. Both values are configurable in the blueprint; neither is a
  hard-coded 1024-token cap.

`llm.prediction.reasoning.parsing` remains enabled with `startString:
" thinking"` and `endString: " response"`. `assemble_blueprint.py` writes
this parser configuration and the reasoning budget to the LM Studio model
JSON. It deliberately does not write `llm.prediction.structured`: that field
controls the interactive GUI default, while benchmark structured output is a
request-level API decision.

`registry_tool.py patch-glm-configs` applies the same parser/budget policy,
preserves an existing GUI structured-output field, removes only stale
` response` stop strings and legacy manual JSON instructions, and excludes
OCR/projector/quarantine configs. The command is therefore safe to run after an LM
Studio update without changing the benchmark/API distinction.

The current runner exception is intentionally limited to GLM-4.7. GLM-4.6V
uses `glm4v_reasoning` and remains on the generic reasoning path until an
independent text/vision API test justifies a narrower override.

## API and direct llama.cpp migration note (2026-09-21)

The Z.AI documentation describes JSON mode as
`response_format={"type":"json_object"}`. That is the provider/API
recommendation and should not be confused with LM Studio's GUI preset field
`llm.prediction.structured`.

LM Studio's own [Structured Output documentation](https://lmstudio.ai/docs/developer/openai-compat/structured-output)
defines the local `/v1/chat/completions` contract more narrowly: it requires a
JSON schema in `response_format.type = "json_schema"` and returns the JSON as
a string in `choices[0].message.content`. For GGUF models, LM Studio states
that the structured-output engine uses llama.cpp's grammar-based sampling.

The local LM Studio OpenAI-compatible endpoint was tested directly on
2026-09-21. It rejected the Z.AI form with HTTP 400:

```text
'response_format.type' must be 'json_schema' or 'text'
```

Therefore the current LM Studio benchmark path uses the supported strict
`json_schema` request shape. The GUI's structured-output field is preserved as
runtime UI state by `registry_tool.py`; it is not used as the benchmark
request's source of truth. If a future LM Studio version accepts
`json_object`, this must be verified by an API smoke test before changing the
runner.

The local observation of an empty final GLM response therefore remains a
deviation from the documented LM Studio response contract, not an argument to
replace `json_schema` with `json_object`. The next diagnostic step is to retain
the complete raw `message` object, including `tool_calls`, `content`, and
reasoning fields, before extraction/classification.

The direct llama.cpp migration introduces a separate control plane. The
`llama-cli` help for the installed build exposes:

```text
--reasoning-format FORMAT
  none             leave thoughts in message.content
  deepseek         put thoughts in message.reasoning_content
  deepseek-legacy  keep <think> tags in message.content and also populate
                   message.reasoning_content
  auto             backend default
```

This option belongs to the direct llama.cpp provider and must not be mapped
directly from the LM Studio parser fields `startString`/`endString`. The
non-streamed `llama-server.exe` comparison for GLM-4.7 has now covered `auto`,
`none`, `deepseek`, and `deepseek-legacy`. A streamed comparison remains
separate because the benchmark's GLM path deliberately uses non-streaming.
The acceptance criteria are a non-empty final response, valid structured
output/code, correct reasoning metadata, and no token-budget truncation.

The LM Studio menu “llama.cpp Arguments Override” is useful for controlled
parameter experiments, including reasoning-related arguments. It is an
experimental GUI override, however, not the provider-neutral registry policy
and not proof that the separately installed llama.cpp binary uses identical
defaults.

## Direct llama.cpp Structured-Output Rule (2026-09-22)

The first direct `llama-server.exe` smoke exposed an important boundary:
LM Studio's strict `json_schema` request must not be copied unchanged into
every llama.cpp request. With a generic Mistral-style template, the schema
grammar can fail before generation with:

```text
Failed to initialize samplers: Unexpected empty grammar stack after accepting piece
```

The direct provider now applies this policy:

* unspecified Structured Output is disabled for llama.cpp; normal models use
  ordinary text responses;
* an explicit structured-output model profile uses the simpler
  `response_format={"type":"json_object"}` request shape;
* `--reasoning-format none` disables constrained JSON as well, because GLM's
  thoughts remain in `message.content` and would be forced through the JSON
  grammar;
* LM Studio keeps its separate `json_schema` contract.

For Unsloth GLM-4.7 Flash Q3_K_S, the post-fix non-streaming smoke completed
without grammar or sampler errors for `auto`, `none`, `deepseek`, and
`deepseek-legacy`. The observed task status was respectively `json_ok`,
`fenced`, `json_ok`, and `json_ok`; all four runs still scored zero on the
single DS1000 task, so this is an infrastructure result, not a quality claim.
The recurring tokenizer warnings about `special_eot_id`/`special_eom_id` and
the default reasoning preservation are model metadata warnings, not request
failures.

The Registry therefore records `reasoning_format: deepseek` for the three
GLM-4.7 deepseek2 entries. This keeps reasoning in
`message.reasoning_content` and leaves the final answer channel available to
the benchmark extractor. GLM-4.6V (`glm4`) remains a separate family and does
not inherit this rule.

Some GLM responses use the native object shape
`{"name":"code","content":"..."}` rather than a `{"code":"..."}`
field. The benchmark extractor accepts both shapes; a syntactically valid
object is not by itself a correctness score.

The current local evidence remains split by model variant:

| Variant                        | Architecture | Local observation                                                                                                                                              |
| ------------------------------ | ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unsloth `GLM 4.7 Flash@Q3_K_S` | `deepseek2`  | Non-streaming request completed without truncation, but the DS1000 run returned empty final content (`tasks_20260921_204117_DS1000_glm-4.7-flash@Q3_K_S.csv`). |
| GLM-4.7 Flash REAP             | `deepseek2`  | The tested DS1000 requests exhausted the configured generation budget before a usable final code response.                                                     |
| GLM-4.6V                       | `glm4`       | Separate family; no GLM-4.7 exception is inferred.                                                                                                             |

The empty-content result is not sufficient evidence to switch the current
LM Studio runner to `json_object`; it is a reason to inspect the raw API
message/tool-call fields and to resolve the behavior in the direct llama.cpp
provider with `--reasoning-format`.

## llama.cpp configuration layers and GLM policy (2026-09-22)

The backend configuration hierarchy is separate from the GLM prompt and
response policy. For the direct llama.cpp backend, the effective order is:

```text
built-in defaults
  -> %APPDATA%\llama.cpp\config.ini          hardware-wide defaults
  -> LLAMA_ARG_* environment variables
  -> llama.cpp preset [*]                     shared router defaults
  -> llama.cpp preset [model]                 model-specific server options
  -> explicit outer CLI options
  -> API request options                       sampling and response format
```

The global Windows user path is `%APPDATA%\llama.cpp\config.ini` (normally
`C:\Users\<user>\AppData\Roaming\llama.cpp\config.ini`). The project keeps
the generated model router preset at
`C:\Users\<user>\.config\llama.cpp\preset.ini`. The Registry remains the
source of truth for GLM identity, architecture, context/KV policy, blueprint,
reasoning format, and benchmark sampling evidence. The preset is only a
derived llama.cpp runtime artifact; it must not be edited as a replacement for
the Registry.

For GLM, the architecture boundary is mandatory:

| Family                       | GGUF architecture | Project policy                                                                              |
| ---------------------------- | ----------------- | ------------------------------------------------------------------------------------------- |
| GLM-4.7 Flash and Flash REAP | `deepseek2`       | `glm_reasoning_coding`, non-streaming comparison, and explicit `reasoning-format` handling  |
| GLM-4.6V                     | `glm4`            | Separate text/vision path; do not inherit the GLM-4.7 exception without an independent test |

The three GLM-4.7 `deepseek2` Registry entries currently use
`reasoning_format: deepseek`, which keeps the thought trace in
`message.reasoning_content` and leaves the final answer in the normal content
channel. `auto`, `none`, `deepseek`, and `deepseek-legacy` remain explicit
diagnostic variants, not four interchangeable defaults. Structured output is
only enabled where the model profile and response path have been tested; a
generic grammar must not be forced through a reasoning stream.

### GLM sampling policy

The official [GLM-4.7 settings](https://z.ai/blog/glm-4.7) distinguish the
benchmark task families from the general default:

| Project category       | Current policy                    | Evidence interpretation                                                                    |
| ---------------------- | --------------------------------- | ------------------------------------------------------------------------------------------ |
| Knowledge / most tasks | `temperature: 1.0`, `top_p: 0.95` | Directly documented default                                                                |
| Coding                 | `temperature: 0.7`, `top_p: 1.0`  | Direct Terminal Bench / SWE-bench Verified setting                                         |
| Math                   | `temperature: 0.7`, `top_p: 1.0`  | Derived from the explicit coding setting; not claimed as a separate Z.AI math prescription |
| Agentic / τ²-Bench     | `temperature: 0`                  | Direct τ²-Bench temperature; Z.AI does not specify `top_p` in that footnote                |

The Registry therefore does not invent an official agentic `top_p` value. If a
runtime needs a complete sampling request, the fallback must remain visible as
a runtime default rather than being recorded as direct manufacturer evidence.
`sampling_research.py` recognizes concrete benchmark names such as Terminal
Bench, SWE-bench, and τ²-Bench and preserves partial profiles; it no longer
requires the source text to use the project's exact category labels. Math is
marked as derived from coding where that is the only supported evidence.

The generation budget is a separate control from sampling temperature. The
current GLM reasoning blueprint uses an 8192-token benchmark response budget
and a distinct 4096-token LM Studio reasoning budget. These are configurable
runtime values and must not be reduced to a blanket 1024-token limit.

### Interpreting recurring llama.cpp warnings

The following messages were observed during local GLM smoke tests:

* `special_eot_id is not in special_eog_ids`
* `special_eom_id is not in special_eog_ids`
* reasoning preservation is enabled

The first two are tokenizer/end-of-generation metadata warnings from the GGUF
model definition. They are not, by themselves, request failures. They become
actionable when generation fails to terminate, terminates too early, or
exhausts the response budget. The reasoning-preservation message describes
the selected template/runtime behavior; it is relevant for multi-turn
agentic traces, but it is not evidence that a JSON response is valid. Inspect
the final content, reasoning channel, stop reason, and token usage together.

For the direct backend, the installed CUDA binary is
`C:\Program Files\llama.cpp\llama-server.exe`. The separate GUI log directory
under `AppData\Local\Llama\logs` is unrelated to the automatic llama.cpp
`config.ini` path. This distinction matters when reproducing a GLM issue:
record the concrete GGUF path, Registry key, preset/config layers, CLI
overrides, API request body, and server log together.



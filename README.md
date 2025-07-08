# STT Telegram Bot

A serverless Telegram bot powered by AWS Lambda that transcribes voice messages, videos, and video notes using the Soniox Speech-to-Text API. The bot supports multiple languages and provides fast, accurate transcriptions directly in your Telegram chats.

## 🚀 Features

- **Multi-format Support**: Transcribes voice messages, videos, and video notes
- **Multi-language**: Supports Russian, Ukrainian, Spanish, and English
- **User Authentication**: Allow-list based access control
- **Serverless Architecture**: Runs on AWS Lambda for cost-effective scaling
- **Error Handling**: Robust error handling with detailed logging
- **Resource Cleanup**: Automatic cleanup of uploaded files and transcriptions
- **Real-time Processing**: Fast transcription with polling for completion

## 📋 Prerequisites

- AWS Account with Lambda access
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- Soniox API Token (from [Soniox](https://soniox.com/))
- Python 3.8+ for local development

## 🛠️ Installation & Deployment

### 1. Create a Telegram Bot

1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Use `/newbot` command and follow instructions
3. Save the bot token for configuration

### 2. Get Soniox API Access

1. Sign up at [Soniox](https://soniox.com/)
2. Obtain your API token from the dashboard
3. Save the token for configuration

### 3. Deploy to AWS Lambda

#### Option A: AWS Console Deployment

1. **Create Lambda Function**:
   ```bash
   # Zip the function code
   zip lambda_function.zip lambda_function.py
   ```

2. **Configure Function**:
   - Runtime: Python 3.8+
   - Handler: `lambda_function.lambda_handler`
   - Timeout: 5 minutes (for large files)
   - Memory: 512 MB

3. **Set Environment Variables** (see Configuration section)

#### Option B: AWS CLI Deployment

```bash
# Create deployment package
zip lambda_function.zip lambda_function.py

# Create IAM role (if needed)
aws iam create-role --role-name lambda-telegram-bot-role \
  --assume-role-policy-document file://trust-policy.json

# Create Lambda function
aws lambda create-function \
  --function-name stt-telegram-bot \
  --runtime python3.9 \
  --role arn:aws:iam::YOUR_ACCOUNT:role/lambda-telegram-bot-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://lambda_function.zip \
  --timeout 300 \
  --memory-size 512
```

### 4. Set Up API Gateway (Optional)

For webhook integration with Telegram:

1. Create API Gateway REST API
2. Create resource and POST method
3. Set integration type to Lambda Function
4. Deploy API and note the endpoint URL

### 5. Configure Telegram Webhook

```bash
# Set webhook URL
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-api-gateway-url.amazonaws.com/stage"}'
```

## ⚙️ Configuration

Set the following environment variables in your Lambda function:

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_TOKEN` | Your Telegram bot token | `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz` |
| `SONIOX_TOKEN` | Your Soniox API token | `your-soniox-api-token` |
| `ALLOW_LIST` | Comma-separated list of authorized usernames | `user1,user2,admin` |

### Environment Variables Setup

**AWS Console**:
1. Go to Lambda → Functions → Your Function
2. Configuration → Environment variables
3. Add the variables listed above

**AWS CLI**:
```bash
aws lambda update-function-configuration \
  --function-name stt-telegram-bot \
  --environment Variables='{
    "TELEGRAM_TOKEN":"your-bot-token",
    "SONIOX_TOKEN":"your-soniox-token",
    "ALLOW_LIST":"user1,user2,admin"
  }'
```

## 📱 Usage

### Bot Commands

The bot automatically processes:
- **Voice Messages**: Send any voice message for transcription
- **Video Files**: Upload video files with audio
- **Video Notes**: Circular video messages with audio
- **Text Messages**: Bot will respond with usage instructions

### Example Interaction

```
User: [Sends voice message in Russian]
Bot: Transcription: Привет, как дела? Сегодня хорошая погода.

User: [Sends video with English speech]
Bot: Transcription: Hello, this is a test video message for transcription.

User: Hello
Bot: You sent text. Please send a voice, video, or video note for transcription.
```

### Supported Languages

- **Russian** (ru)
- **Ukrainian** (uk) 
- **Spanish** (es)
- **English** (en)

The bot automatically detects the language using Soniox's language hints feature.

## 🏗️ Architecture

```
Telegram → API Gateway → AWS Lambda → Soniox API
                            ↓
                    CloudWatch Logs
```

### Data Flow

1. **User sends media** → Telegram delivers to webhook
2. **API Gateway** → Triggers Lambda function
3. **Lambda function**:
   - Validates user authorization
   - Downloads file from Telegram
   - Uploads to Soniox API
   - Starts transcription job
   - Polls for completion
   - Retrieves transcript
   - Cleans up resources
   - Sends result back to user

## 🔧 Technical Details

### Dependencies

The function uses these Python libraries (all available in Lambda runtime):
- `urllib3` - HTTP client for API calls
- `json` - JSON processing
- `logging` - Structured logging
- `os` - Environment variable access
- `time` - Polling delays
- `typing` - Type hints

### Error Handling

- **Network Issues**: Automatic retry with exponential backoff
- **API Errors**: Graceful handling with user-friendly messages
- **Invalid Files**: Clear error messages for unsupported formats
- **Authorization**: Secure user verification
- **Resource Cleanup**: Guaranteed cleanup even on failures

### Performance Considerations

- **Connection Pooling**: Single `urllib3.PoolManager` instance
- **Concurrent Limits**: Soniox API rate limiting respected
- **Memory Optimization**: Streaming file processing
- **Timeout Handling**: 5-minute Lambda timeout for large files

## 📊 Monitoring & Logging

### CloudWatch Logs

The bot logs all activities with different levels:
- **INFO**: Normal operations, user interactions
- **WARNING**: Non-critical issues (failed reply sending)
- **ERROR**: Errors with detailed stack traces

### Log Examples

```
INFO: Received event
INFO: Sending reply to chat_id 123456: 'Transcription: Hello world...'
INFO: Deleted transcription trans_xyz123
INFO: Deleted file file_abc789
ERROR: Failed to send reply to chat_id 123456: Connection timeout
```

### Monitoring Metrics

Monitor these CloudWatch metrics:
- Lambda invocations
- Duration
- Errors
- Throttles
- Memory utilization

## 🔒 Security

### Best Practices Implemented

- **Environment Variables**: Sensitive tokens stored securely
- **User Authorization**: Allow-list based access control
- **Input Validation**: All inputs validated before processing
- **Error Handling**: No sensitive data leaked in error messages
- **Resource Cleanup**: No data persistence on Soniox servers

### Recommended Security Measures

1. **IAM Roles**: Use least-privilege IAM roles
2. **VPC**: Deploy Lambda in VPC for network isolation
3. **Encryption**: Enable encryption at rest for environment variables
4. **Monitoring**: Set up CloudWatch alarms for unusual activity

## 🐛 Troubleshooting

### Common Issues

**Bot not responding**:
- Check webhook configuration
- Verify environment variables
- Check CloudWatch logs

**"User not authorized" message**:
- Verify username in `ALLOW_LIST`
- Check for typos in usernames

**Transcription failures**:
- Verify Soniox API token
- Check file format support
- Monitor API rate limits

**Timeout errors**:
- Increase Lambda timeout (max 15 minutes)
- Check file size limits

### Debug Mode

Enable detailed logging by adding environment variable:
```
LOG_LEVEL=DEBUG
```

## 📄 API Reference

### Webhook Payload

The bot expects Telegram webhook payloads:

```json
{
  "update_id": 123456789,
  "message": {
    "message_id": 1,
    "from": {
      "id": 123456789,
      "username": "user123"
    },
    "chat": {
      "id": 123456789,
      "type": "private"
    },
    "voice": {
      "file_id": "BAADBAADxQEAAuCjggPFV8ILbJdaFAI",
      "mime_type": "audio/ogg"
    }
  }
}
```

### Response Format

```json
{
  "statusCode": 200,
  "body": "\"Transcription: Your transcribed text here\""
}
```

## 🔄 Development

### Local Testing

1. **Set environment variables**:
   ```bash
   export TELEGRAM_TOKEN="your-token"
   export SONIOX_TOKEN="your-token"
   export ALLOW_LIST="your-username"
   ```

2. **Create test event**:
   ```python
   test_event = {
       "body": json.dumps({
           "message": {
               "chat": {"id": 123},
               "from": {"username": "testuser"},
               "voice": {
                   "file_id": "test_file_id",
                   "mime_type": "audio/ogg"
               }
           }
       })
   }
   ```

3. **Run locally**:
   ```python
   from lambda_function import lambda_handler
   result = lambda_handler(test_event, None)
   print(result)
   ```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Soniox](https://soniox.com/) for the excellent Speech-to-Text API
- [Telegram Bot API](https://core.telegram.org/bots/api) for the messaging platform
- AWS Lambda for serverless computing

---

**Need help?** Open an issue or contact the maintainers!

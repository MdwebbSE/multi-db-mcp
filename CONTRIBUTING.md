# Contributing to Multi-DB MCP

Thank you for your interest in contributing to this project!

## How to Contribute

### Reporting Bugs

1. Check if the bug has already been reported
2. Create a detailed issue with:
   - Clear title and description
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details

### Suggesting Features

1. Open an issue with `[Feature Request]` prefix
2. Describe the use case
3. Explain how it should work
4. Consider backward compatibility

### Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests if applicable
5. Ensure code quality
6. Commit with clear messages
7. Push to your fork
8. Submit a Pull Request

## Development Setup

```bash
# Clone the repository
git clone https://github.com/your-username/multi-db-mcp.git
cd multi-db-mcp

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install pymysql mssql-python starlette "mcp>=1.0"

# Run the server
python server.py
```

## Code Style

- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and small

## Security Considerations

- Never commit credentials or secrets
- Use environment variables for sensitive data
- Validate all user inputs
- Follow security best practices

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

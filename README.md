# Multi-Database MCP Server

A Model Context Protocol (MCP) HTTP server that provides database query tools for MySQL and MSSQL databases with connection pooling, authentication, and rate limiting.

## Features

- **Multi-Database Support**: Connect to MySQL and MSSQL databases
- **MCP Protocol**: Exposes database tools via the Model Context Protocol
- **Connection Pooling**: Efficient connection reuse for better performance
- **Authentication**: Bearer token authentication (configurable)
- **Rate Limiting**: Built-in rate limiting to prevent abuse
- **Read-Only Mode**: Optional read-only mode for safety
- **Row Limits**: Configurable maximum rows per query
- **Transport Security**: DNS rebinding protection and CORS support

## Python Environment Setup

### Prerequisites

- **Python**: Version 3.9 or higher

### Setting Up Virtual Environment

**Create a virtual environment (recommended):**

```bash
# Navigate to the project directory
cd /path/to/multi-db-mcp

# Create virtual environment
python -m venv venv

# Activate
source venv/bin/activate
```

**Verify activation:**
```bash
# Should show (venv) prefix
python --version
```

### Installing Dependencies

```bash
# Upgrade pip first (recommended)
pip install --upgrade pip

# Install required packages
pip install -r requirements.txt

# Verify installation
pip list | grep -E "pymysql|mssql|starlette|mcp|uvicorn"
```
---
### Run the Server

```bash
uvicorn server:app --host 0.0.0.0 --port 8001
```

## Service Installation

### Running as a Linux Service (systemd)

1. Create a systemd service file:
   ```bash
   sudo nano /etc/systemd/system/multi-db-mcp.service
   ```

2. Add the following content:
   ```ini
   [Unit]
   Description=Multi-Database MCP Server
   After=network.target
   
   [Service]
   Type=simple
   User=www-data
   Group=www-data
   WorkingDirectory=/path/to/multi-db-mcp
   Environment="PATH=/path/to/multi-db-mcp/venv/bin"
   Environment="DB_SERVERS_CONFIG=/path/to/multi-db-mcp/db_servers.json"
   Environment="DB_READ_ONLY=true"
   ExecStart=/path/to/multi-db-mcp/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000
   Restart=always
   RestartSec=10
   
   [Install]
   WantedBy=multi-user.target
   ```

3. Install and enable the service:
   ```bash
   sudo chown -R www-data:www-data /path/to/multi-db-mcp
   
   sudo systemctl daemon-reload
   sudo systemctl enable multi-db-mcp
   sudo systemctl start multi-db-mcp
   ```

4. Check service status:
   ```bash
   sudo systemctl status multi-db-mcp
   sudo journalctl -u multi-db-mcp -f
   ```

## Quick Start

### 1. Configure Database Servers

Edit [`db_servers.json`](db_servers.json) to configure your database connections:

```json
{
  "transport_security": {
    "enable_dns_rebinding_protection": true,
    "allowed_hosts": ["localhost:*", "127.0.0.1:*"],
    "allowed_origins": ["http://localhost:*", "http://127.0.0.1:*"]
  },
  "servers": {
    "main-mysql": {
      "engine": "mysql",
      "host": "your-mysql-host",
      "port": 3306,
      "user": "username",
      "password": "password",
      "allowed_databases": ["mydb"],
      "allowed_tables": {
        "mydb": ["users", "orders"]
      },
      "connect_timeout": 10
    },
    "main-mssql": {
      "engine": "mssql",
      "host": "your-mssql-host",
      "port": 1433,
      "user": "username",
      "password": "password",
      "allowed_databases": ["mydb"],
      "encrypt": true,
      "trust_server_certificate": false,
      "connect_timeout": 10
    }
  }
}
```

#### Configuration Options

| Option | Required | Description |
|--------|----------|-------------|
| `engine` | Yes | Database engine: `mysql` or `mssql` |
| `host` | Yes | Database server hostname |
| `port` | Yes | Database server port |
| `user` | Yes | Username for authentication |
| `password` | Yes | Password for authentication |
| `allowed_databases` | No | List of databases this server can access |
| `allowed_tables` | No | Object mapping database names to lists of allowed tables. Restricts `preview_table` and `select_where` tools to specific tables. |
| `connect_timeout` | No | Connection timeout in seconds (default: 10) |
| `encrypt` | No | Enable encryption (MSSQL only) |
| `trust_server_certificate` | No | Trust server certificate (MSSQL only) |

### 2. Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_SERVERS_CONFIG` | `./db_servers.json` | Path to configuration file |
| `DB_READ_ONLY` | `true` | Enable read-only mode |
| `DB_MAX_ROWS` | `200` | Maximum rows returned per query |
| `DB_POOL_MAX_CONNECTIONS` | `10` | Max connections per pool |
| `DB_POOL_MIN_CONNECTIONS` | `2` | Min connections per pool |
| `DB_POOL_RECYCLE_SECONDS` | `3600` | Connection recycle time |
| `MCP_BEARER_TOKEN` | (none) | Bearer token for authentication |
| `RATE_LIMIT_REQUESTS` | `100` | Requests per rate limit window |
| `RATE_LIMIT_WINDOW` | `60` | Rate limit window in seconds |

## Available MCP Tools

### `list_tables`
List all tables in a database.

**Parameters:**
- `db_server` (optional): Database server name from config
- `database` (optional): Database name
- `schema` (optional): Schema name (for MSSQL, defaults to 'dbo')

### `describe_table`
Get column information for a table.

**Parameters:**
- `table_name`: Name of the table
- `db_server` (optional): Database server name
- `database` (optional): Database name
- `schema` (optional): Schema name

### `run_query`
Execute a SQL query.

**Parameters:**
- `sql`: SQL query to execute
- `db_server` (optional): Database server name
- `database` (optional): Database name

**Note:** In read-only mode, only SELECT/SHOW/DESCRIBE/EXPLAIN/WITH queries are allowed.

### `preview_table`
Preview rows from a table.

**Parameters:**
- `table_name`: Name of the table
- `limit` (optional): Number of rows (default: 50, max: 200)
- `db_server` (optional): Database server name
- `database` (optional): Database name

### `select_where`
Select rows with filters.

**Parameters:**
- `table_name`: Name of the table
- `filters`: Dictionary of column=value filters
- `limit` (optional): Number of rows (default: 50, max: 200)
- `db_server` (optional): Database server name
- `database` (optional): Database name

### `list_columns`
List columns of a table.

**Parameters:**
- `table_name`: Name of the table
- `db_server` (optional): Database server name
- `database` (optional): Database name
- `schema` (optional): Schema name

### `get_current_database`
Get the default db_server and database from request headers.

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Health check - returns server status |
| `GET /health` | Detailed health check with server config |
| `POST /` | MCP protocol endpoint |

## Authentication

When `MCP_BEARER_TOKEN` is set, all endpoints except `/` and `/health` require a Bearer token:

```bash
curl -H "Authorization: Bearer your-token" http://localhost:8001/health
```

## Security Considerations

- Always use strong bearer tokens (minimum 10 characters)
- Keep credentials secure and never commit to version control
- Use SSL/TLS encryption for database connections
- Consider using read-only mode in production
- Configure appropriate rate limits for your use case

## Database User Security

### Dedicated Database Users

It is strongly recommended to create dedicated database users specifically for the MCP server rather than using existing application or administrative accounts. These dedicated users should have minimal permissions required for the server's functionality.

### MySQL Permissions

For MySQL databases, the following minimal permissions are recommended:

```sql
-- Grant only necessary permissions
GRANT SELECT, SHOW VIEW, EXECUTE ON your_database.* TO 'mcp_user'@'host';
```

Required permissions:
- `SELECT` - Required for reading data from tables
- `SHOW VIEW` - Required for the `list_tables` tool to work properly
- `EXECUTE` - Required if using stored procedures

### MSSQL Permissions

For MSSQL databases, the following minimal permissions are recommended:

```sql
-- Create a user with only necessary permissions
USE your_database;
CREATE USER 'mcp_user' FOR LOGIN 'mcp_login';
GRANT SELECT ON SCHEMA::dbo TO 'mcp_user';
```

Required permissions:
- `SELECT` on relevant schemas - Required for reading data from tables

### Additional Security Measures

- Create separate users for each database if possible
- Restrict access by host (`'mcp_user'@'localhost'` or specific IP)
- Use strong, unique passwords for each database user
- Regularly audit user permissions
- Consider using database roles for permission management

## Input Safety Disclaimer

The MCP Server includes measures to attempt to prevent malicious code execution, including:
- Query sanitization
- Read-only mode enforcement
- Rate limiting

However, **it is ultimately the user's responsibility to ensure that all input provided to the database queries is safe and properly validated**. The server cannot guarantee protection against all forms of SQL injection or malicious input that may be crafted by sophisticated attackers. Always validate and sanitize input on the client side before sending queries through the MCP Server, especially when accepting user-generated content.

## Project Structure

```
multi-db-mcp/
├── server.py           # Main HTTP server entry point
├── tools.py            # MCP tool definitions
├── db.py               # Database connections and helpers
├── config.py           # Configuration loading
├── middleware.py       # Auth and rate limiting
├── db_servers.json     # Database configuration
└── README.md           # This file
```

## License

MIT License - see LICENSE file for details.

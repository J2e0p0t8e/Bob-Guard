# Bob-Guard 🛡️

**Automated Compliance & Security Analysis Agent for Legacy Codebases**

Bob-Guard is an intelligent agent that analyzes legacy codebases to detect compliance violations (GDPR, HIPAA, internal security policies) and security vulnerabilities, then automatically proposes and applies fixes using IBM Bob API.

## 🎯 Features

- **Compliance Analysis**: Detect GDPR, HIPAA, and custom compliance violations
- **Security Scanning**: Identify security vulnerabilities and code smells
- **Automated Remediation**: Generate and apply fixes automatically
- **Test Generation**: Create unit tests for remediated code
- **Interactive Reports**: Generate detailed HTML reports with findings
- **Web Interface**: User-friendly Flask-based web UI
- **CLI Support**: Command-line interface for automation
- **IBM Bob Integration**: Leverage IBM Bob API for intelligent code analysis

## 📁 Project Structure

```
bob-guard/
├── src/
│   ├── analyzer.py          # Code analysis engine
│   ├── remediator.py        # Automated fix application
│   ├── test_generator.py    # Unit test generation
│   ├── reporter.py          # Report generation
│   └── bob_client.py        # IBM Bob API client
├── config/
│   └── rules.json           # Compliance rules configuration
├── tests/
│   └── sample_repo/         # Sample test repositories
├── output/                  # Generated reports
├── logs/                    # Application logs
├── templates/
│   ├── index.html           # Main web interface
│   ├── results.html         # Analysis results page
│   └── chat.html            # Interactive chat interface
├── static/
│   ├── style.css            # Web UI styling
│   └── script.js            # Frontend logic
├── app.py                   # Flask web server
├── main.py                  # CLI orchestrator
├── requirements.txt         # Python dependencies
└── .env.example             # Environment variables template
```

## 🚀 Getting Started

### Prerequisites

- Python 3.9 or higher
- IBM Bob API access credentials
- Git (for repository analysis)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/bob-guard.git
cd bob-guard
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Configure environment variables:
```bash
cp .env.example .env
# Edit .env with your IBM Bob API credentials
```

### Configuration

Edit `config/rules.json` to customize compliance rules:

```json
{
  "gdpr": {
    "enabled": true,
    "rules": []
  },
  "hipaa": {
    "enabled": true,
    "rules": []
  },
  "security": {
    "enabled": true,
    "rules": []
  }
}
```

## 💻 Usage

### Web Interface

Start the Flask web server:

```bash
python app.py
```

Navigate to `http://localhost:5000` in your browser.

### Command Line Interface

Analyze a repository:

```bash
python main.py analyze --repo /path/to/repo --output ./output/report.html
```

You can also pass a GitHub repository URL and the CLI will clone it before analysis:

```bash
python main.py --repo https://github.com/user/repository --output ./output
```

Apply fixes automatically:

```bash
python main.py remediate --repo /path/to/repo --auto-apply
```

Generate tests:

```bash
python main.py generate-tests --repo /path/to/repo
```

Full pipeline:

```bash
python main.py run --repo /path/to/repo --auto-fix --generate-tests
```

## 🔧 Architecture

Bob-Guard follows a modular architecture with single responsibility principle:

- **Analyzer**: Scans code for compliance and security issues
- **Remediator**: Generates and applies fixes using IBM Bob API
- **Test Generator**: Creates unit tests for modified code
- **Reporter**: Produces detailed HTML/JSON reports
- **Bob Client**: Handles communication with IBM Bob API

## 📊 Compliance Standards

- **GDPR**: Data privacy, consent management, data retention
- **HIPAA**: Protected Health Information (PHI) handling
- **Security**: SQL injection, XSS, authentication, encryption
- **Custom Rules**: Define your own compliance requirements

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- IBM Bob API for intelligent code analysis
- Open-source security tools: Bandit, Semgrep, Safety
- Flask framework for web interface

## 📧 Contact

For questions or support, please open an issue on GitHub.

---

**Built with ❤️ for secure and compliant code**
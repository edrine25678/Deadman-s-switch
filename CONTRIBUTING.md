# Contributing to Deadman's Switch

Thank you for your interest in contributing to the Deadman's Switch project! This document provides guidelines and instructions for contributing.

## 🤝 How to Contribute

### Reporting Bugs

Before creating bug reports, please check the existing issues to avoid duplicates. When creating a bug report, include:

- **Clear title and description** of the problem
- **Steps to reproduce** the issue
- **Expected behavior** vs **actual behavior**
- **Screenshots** if applicable
- **Environment information**:
  - OS version
  - Python version
  - Relevant dependency versions
- **Log files** (redact sensitive information)

### Suggesting Enhancements

Enhancement suggestions are welcome! Please:

- Use a clear and descriptive title
- Provide a detailed description of the proposed enhancement
- Explain why this enhancement would be useful
- Consider including implementation suggestions if applicable

### Pull Requests

#### Process

1. **Fork the repository** and create your branch from `main`
2. **Make your changes** following the coding standards
3. **Add tests** for new functionality
4. **Update documentation** as needed
5. **Ensure all tests pass**
6. **Submit your pull request** with a clear description

#### PR Guidelines

- **One feature per PR** - Keep changes focused
- **Clear commit messages** - Use conventional commit format
- **Update tests** - Ensure test coverage remains high
- **Documentation** - Update relevant documentation
- **No merge commits** - Use rebase/squash as appropriate

## 🛠️ Development Setup

### Prerequisites

- Python 3.8+
- Git
- Virtual environment (recommended)

### Setup Steps

```bash
# Clone your fork
git clone https://github.com/yourusername/guard_pro.git
cd guard_pro

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-cov  # For testing

# Install in development mode
pip install -e .
```

### Running Tests

```bash
# Run all tests
python -m pytest

# Run specific test file
python -m pytest test_guard.py -v

# Run with coverage
python -m pytest --cov=.

# Run integration tests
python -m unittest test_integration.py -v
```

### Code Style

- Follow PEP 8 guidelines
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and small
- Add comments for complex logic

## 📝 Coding Standards

### Python Style

- **Indentation**: 4 spaces (no tabs)
- **Line length**: Maximum 100 characters
- **Imports**: Group imports (standard library, third-party, local)
- **Naming**: 
  - Functions/variables: `snake_case`
  - Classes: `PascalCase`
  - Constants: `UPPER_SNAKE_CASE`

### Documentation

- **Docstrings**: Use Google style or NumPy style
- **Comments**: Explain "why", not "what"
- **README**: Update for user-facing changes
- **Code comments**: Keep them up-to-date

### Testing

- **Unit tests**: Test individual functions
- **Integration tests**: Test component interactions
- **Coverage**: Aim for >80% coverage
- **Edge cases**: Test error conditions

## 🚀 Project Structure

```
guard_pro/
├── Core Components
│   ├── main_guard.py         # Main monitoring logic
│   ├── watchdog.py           # Process monitoring
│   └── install.py            # Installation/uninstallation
├── Configuration
│   ├── config_ui.py          # GUI configuration
│   ├── validate_config.py    # Configuration validation
│   ├── calibrate.py          # Keystroke calibration
│   └── calibrate_face.py     # Face calibration
├── Testing
│   ├── test_guard.py         # Unit tests
│   ├── test_integration.py   # Integration tests
│   └── test_full_system.py   # Full system tests
└── Documentation
    ├── README.md             # Main documentation
    ├── CONTRIBUTING.md       # This file
    ├── LICENSE               # License information
    └── SECURITY.md           # Security policy
```

## 🔒 Security Considerations

### Security Issues

**Do not** report security vulnerabilities via public issues. Instead:

1. Send an email to: security@example.com
2. Include "Security Vulnerability" in the subject
3. Provide details about the vulnerability
4. Wait for acknowledgment before disclosing

### Security Guidelines

- Never commit sensitive data (API keys, passwords)
- Use environment variables for configuration
- Validate all user inputs
- Keep dependencies updated
- Follow the principle of least privilege

## 📋 Release Process

### Versioning

We follow [Semantic Versioning](https://semver.org/):
- **MAJOR**: Breaking changes
- **MINOR**: New features (backwards compatible)
- **PATCH**: Bug fixes (backwards compatible)

### Release Checklist

- [ ] All tests passing
- [ ] Documentation updated
- [ ] Changelog updated
- [ ] Version number updated
- [ ] Security review completed
- [ ] Release notes prepared

## 🎯 Areas for Contribution

### High Priority

- **Linux/macOS support** - Port to other platforms
- **Improved documentation** - Tutorials, examples
- **Test coverage** - Increase test coverage
- **Bug fixes** - Address open issues

### Medium Priority

- **Performance improvements** - Optimize bottlenecks
- **UI enhancements** - Improve configuration wizard
- **Additional features** - New detection methods
- **Localization** - Multi-language support

### Low Priority

- **Code refactoring** - Improve code structure
- **Dependency updates** - Keep libraries current
- **Documentation polish** - Improve clarity

## 💬 Communication

- **GitHub Issues**: For bugs and feature requests
- **GitHub Discussions**: For questions and ideas  
- **Pull Requests**: For code contributions
- **Email**: For security issues only (see SECURITY.md)

## 📜 Code of Conduct

### Our Pledge

We are committed to providing a welcoming and inclusive environment for all contributors.

### Our Standards

- **Resful communication** - Be kind and constructive
- **Inclusive language** - Avoid exclusionary terms
- **Accepting feedback** - Listen and learn from others
- **Focus on what is best** - Prioritize the community

### Responsibilities

- **Be respectful** - Treat others with respect
- **Be inclusive** - Welcome all contributors
- **Be collaborative** - Work together effectively
- **Be constructive** - Provide helpful feedback

### Enforcement

Project maintainers reserve the right to remove comments or contributions that do not align with this Code of Conduct.

## 🏆 Recognition

Contributors will be recognized in:
- CONTRIBUTORS.md file
- Release notes
- Project documentation

## 📄 License

By contributing, you agree that your contributions will be licensed under the MIT License.

## ❓ Questions?

- Check existing [GitHub Issues](https://github.com/yourusername/guard_pro/issues)
- Start a [GitHub Discussion](https://github.com/yourusername/guard_pro/discussions)
- Contact maintainers via email for sensitive matters

---

**Thank you for contributing to Deadman's Switch!** 🎉

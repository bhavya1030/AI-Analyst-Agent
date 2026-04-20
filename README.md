# AI Analyst Agent

An agentic AI workflow for intelligent data analysis using Large Language Models (LLMs). This project provides a comprehensive platform for automated data exploration, visualization, and insights generation through conversational AI.

## Features

- **Intelligent Data Analysis**: Automated exploratory data analysis (EDA) with AI-driven insights
- **Conversational Interface**: Chat-based interaction for natural language queries about your data
- **Automated Visualization**: AI-powered chart generation and selection using Plotly
- **Data Cleaning & Preprocessing**: Intelligent data cleaning agents for data preparation
- **Hypothesis Testing**: Automated hypothesis generation and testing
- **Forecasting**: Time series analysis and forecasting capabilities
- **Pattern Detection**: Machine learning-based pattern recognition in datasets
- **Multi-format Support**: Support for CSV, Excel, and other common data formats
- **Real-time Processing**: FastAPI backend for efficient data processing
- **Modern UI**: Next.js-based responsive web interface with interactive charts

## Tech Stack

### Backend
- **Python 3.8+**
- **FastAPI**: High-performance web framework
- **LangChain & LangGraph**: Agent orchestration and workflow management
- **Pandas & NumPy**: Data manipulation and analysis
- **Plotly**: Data visualization
- **SQLAlchemy**: Database operations

### Frontend
- **Next.js 14**: React framework with App Router
- **TypeScript**: Type-safe JavaScript
- **Tailwind CSS**: Utility-first CSS framework
- **Plotly.js**: Interactive charts and graphs
- **Zustand**: State management
- **Axios**: HTTP client

### Testing
- **Jest**: Unit testing for frontend
- **Playwright**: End-to-end testing
- **Pytest**: Backend testing

## Installation

### Prerequisites
- Python 3.8 or higher
- Node.js 18 or higher
- npm or yarn

### Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd backend
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

4. Set up environment variables:
   Create a `.env` file in the backend directory with your API keys:
   ```
   OPENAI_API_KEY=your_openai_api_key_here
   # Add other required environment variables
   ```

### Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd analytics-copilot-ui
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start the development server:
   ```bash
   npm run dev
   ```

### Running the Application

1. Start the backend server:
   ```bash
   cd backend
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   uvicorn main:app --reload
   ```

2. Start the frontend (in a new terminal):
   ```bash
   cd analytics-copilot-ui
   npm run dev
   ```

3. Open your browser and navigate to `http://localhost:3000`

## Usage

1. **Upload Data**: Use the upload interface to import your CSV or Excel files
2. **Chat with AI**: Ask questions about your data in natural language
3. **View Insights**: Get automated analysis, visualizations, and recommendations
4. **Explore Patterns**: Discover trends, correlations, and anomalies
5. **Generate Reports**: Export analysis results and visualizations

### Example Queries
- "What are the key trends in this dataset?"
- "Show me a correlation analysis between sales and marketing spend"
- "Create a forecast for the next 6 months"
- "Identify any outliers in the data"
- "Generate a summary report of the dataset"

## Project Structure

```
├── analytics-copilot-ui/          # Next.js frontend application
│   ├── app/                       # Next.js app directory
│   ├── components/                # Reusable React components
│   ├── hooks/                     # Custom React hooks
│   ├── services/                  # API service functions
│   ├── store/                     # Zustand state management
│   ├── types/                     # TypeScript type definitions
│   └── utils/                     # Utility functions
├── backend/                       # FastAPI backend application
│   ├── agents/                    # AI agent implementations
│   ├── cache/                     # Caching mechanisms
│   ├── core/                      # Core utilities and logging
│   ├── graph/                     # Workflow graph definitions
│   ├── tools/                     # Data processing tools
│   └── utils/                     # Backend utilities
├── data/                          # Sample datasets
├── tests/                         # Test suites
└── requirements.txt               # Python dependencies
```

## API Documentation

Once the backend is running, visit `http://localhost:8000/docs` for interactive API documentation powered by Swagger UI.

## Testing

### Backend Tests
```bash
cd backend
python -m pytest tests/
```

### Frontend Tests
```bash
cd analytics-copilot-ui
npm test
```

### End-to-End Tests
```bash
cd analytics-copilot-ui
npm run test:e2e
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes and add tests
4. Run the test suite: `npm test` and `python -m pytest tests/`
5. Commit your changes: `git commit -am 'Add some feature'`
6. Push to the branch: `git push origin feature/your-feature-name`
7. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [LangChain](https://www.langchain.com/) for agent orchestration
- Visualization powered by [Plotly](https://plotly.com/)
- UI components from [Tailwind CSS](https://tailwindcss.com/)

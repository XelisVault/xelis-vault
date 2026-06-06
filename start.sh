#!/bin/bash

# XELIS Vault Website — Quick Start Script

echo "=================================="
echo "XELIS Vault — Website Quick Start"
echo "=================================="
echo ""

# Check Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found. Please install Node.js 16+"
    exit 1
fi

echo "✅ Node.js $(node --version) found"
echo ""

# Navigate to dashboard
cd dashboard

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
    echo ""
fi

# Ask user what to do
echo "What would you like to do?"
echo "1) Start development server (npm run dev)"
echo "2) Build for production (npm run build)"
echo "3) Preview production build (npm run preview)"
echo ""
read -p "Choose option [1-3]: " choice

case $choice in
    1)
        echo ""
        echo "🚀 Starting development server..."
        echo "📱 Open http://localhost:5173 in your browser"
        echo "   Press Ctrl+C to stop"
        echo ""
        npm run dev
        ;;
    2)
        echo ""
        echo "🏗️  Building for production..."
        npm run build
        echo ""
        echo "✅ Build complete! Output in: dashboard/dist/"
        echo ""
        echo "Ready to deploy to:"
        echo "  • Vercel: vercel deploy"
        echo "  • Netlify: Upload dist/ folder"
        echo "  • GitHub Pages: Push dist/ to gh-pages"
        echo "  • Self-hosted: Copy dist/ to web server"
        ;;
    3)
        echo ""
        echo "📦 Building and previewing..."
        npm run build
        echo ""
        echo "🌐 Starting preview server..."
        echo "   Press Ctrl+C to stop"
        echo ""
        npm run preview
        ;;
    *)
        echo "❌ Invalid choice"
        exit 1
        ;;
esac

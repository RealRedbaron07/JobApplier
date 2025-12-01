#!/bin/bash
# Script to push JobApplier to GitHub

echo "=========================================="
echo "🚀 Pushing JobApplier to GitHub"
echo "=========================================="
echo ""

# Check if git is initialized
if [ ! -d ".git" ]; then
    echo "❌ Git not initialized. Run: git init"
    exit 1
fi

# Check if we have a remote
if git remote | grep -q origin; then
    echo "✅ Remote 'origin' already exists"
    REMOTE_URL=$(git remote get-url origin)
    echo "   Current remote: $REMOTE_URL"
    echo ""
    read -p "Do you want to use this remote? (yes/no): " use_existing
    if [ "$use_existing" != "yes" ] && [ "$use_existing" != "y" ]; then
        echo "Please set up your remote manually or remove it first:"
        echo "  git remote remove origin"
        exit 1
    fi
else
    echo "📝 No remote configured yet."
    echo ""
    echo "Please create a GitHub repository first:"
    echo "  1. Go to: https://github.com/new"
    echo "  2. Repository name: JobApplier"
    echo "  3. Choose: Private (recommended)"
    echo "  4. DO NOT initialize with README"
    echo "  5. Click 'Create repository'"
    echo ""
    read -p "Enter your GitHub username: " GITHUB_USERNAME
    read -p "Enter repository name (default: JobApplier): " REPO_NAME
    REPO_NAME=${REPO_NAME:-JobApplier}
    
    echo ""
    echo "Adding remote: https://github.com/$GITHUB_USERNAME/$REPO_NAME.git"
    git remote add origin "https://github.com/$GITHUB_USERNAME/$REPO_NAME.git"
fi

echo ""
echo "📦 Checking git status..."
git status --short | head -10

echo ""
echo "🔄 Setting branch to 'main'..."
git branch -M main

echo ""
echo "📤 Pushing to GitHub..."
echo ""

# Try to push
if git push -u origin main; then
    echo ""
    echo "=========================================="
    echo "✅ Successfully pushed to GitHub!"
    echo "=========================================="
    echo ""
    REMOTE_URL=$(git remote get-url origin)
    echo "Your repository is now at:"
    echo "  $REMOTE_URL"
    echo ""
else
    echo ""
    echo "=========================================="
    echo "❌ Push failed"
    echo "=========================================="
    echo ""
    echo "Possible reasons:"
    echo "  1. Repository doesn't exist on GitHub yet"
    echo "  2. Authentication required (GitHub login)"
    echo "  3. Wrong repository URL"
    echo ""
    echo "To fix:"
    echo "  1. Create repo at: https://github.com/new"
    echo "  2. Or check your remote: git remote -v"
    echo "  3. Or set remote: git remote set-url origin <URL>"
    exit 1
fi


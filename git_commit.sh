#!/bin/bash
# Simple git helper script for manual commits

echo "=================================="
echo "Git Commit Helper"
echo "=================================="
echo ""

# Show current status
echo "📊 Current status:"
git status --short
echo ""

# Ask for commit message
read -p "Enter commit message (or press Enter to skip): " commit_msg

if [ -z "$commit_msg" ]; then
    echo "❌ No commit message provided. Exiting."
    exit 1
fi

# Add all changes
echo ""
echo "📦 Adding all changes..."
git add .

# Commit
echo "💾 Committing changes..."
git commit -m "$commit_msg"

# Show status
echo ""
echo "✅ Commit complete!"
echo ""
echo "📊 Current status:"
git status --short
echo ""
echo "💡 To push to remote, run: git push"
echo ""

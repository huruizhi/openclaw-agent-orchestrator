#!/usr/bin/env python3
"""
X (Twitter) Updates Monitor - Collects important updates every 2 hours
Uses browser automation to browse X platform and official blog
Sends summaries to Discord lab channel via discord-notify
"""

import os
import sys
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# Add skills path for imports
SKILLS_PATH = "/home/ubuntu/.openclaw/skills"
sys.path.insert(0, f"{SKILLS_PATH}/discord-notify/scripts")

# Configuration
LAB_CHANNEL_ID = os.getenv("LAB_CHANNEL_ID", "1466602081816416455")  # Default to #agi
DISCORD_NOTIFY_SCRIPT = f"{SKILLS_PATH}/discord-notify/scripts/discord_notify.py"

def browse_x_updates():
    """Browse X/Twitter to collect important platform updates using openclaw managed browser"""
    try:
        # Use openclaw managed browser (not Chrome extension relay)
        # Start openclaw browser profile
        subprocess.run(["openclaw", "browser", "start", "--profile", "openclaw"], timeout=15)
        
        # Navigate to X/Twitter explore page for trending updates
        cmd = ["openclaw", "browser", "navigate", "--url", "https://x.com/explore", "--profile", "openclaw"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            return [f"Failed to navigate to X: {result.stderr}"]
        
        # Take snapshot to extract content
        cmd = ["openclaw", "browser", "snapshot", "--format", "markdown", "--profile", "openclaw"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            # Parse snapshot content for trending topics
            content = result.stdout
            # Extract relevant information (simplified)
            updates = [content[:1500]]  # Take first portion
            
            # Also check X's official blog or news section
            cmd2 = ["openclaw", "browser", "navigate", "--url", "https://blog.x.com", "--profile", "openclaw"]
            result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=30)
            
            if result2.returncode == 0:
                cmd3 = ["openclaw", "browser", "snapshot", "--format", "markdown", "--profile", "openclaw"]
                result3 = subprocess.run(cmd3, capture_output=True, text=True, timeout=30)
                if result3.returncode == 0:
                    updates.append(result3.stdout[:1500])
            
            return updates
        else:
            return [f"Failed to get X updates: {result.stderr}"]
            
    except subprocess.TimeoutExpired:
        return ["Error: Browser operation timed out"]
    except Exception as e:
        return [f"Error collecting X updates: {str(e)}"]

def format_summary(results):
    """Format search results into a readable summary"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    summary = f"**📊 X Platform Updates Summary**\n"
    summary += f"⏰ {timestamp} (4-hour window)\n\n"
    
    # Simple formatting of results
    for i, result in enumerate(results, 1):
        summary += f"**Source {i}:**\n"
        # Take first 500 chars of each result
        summary += result[:500] + "...\n\n"
    
    summary += "---\n"
    summary += "_Collected by automated monitor_"
    
    return summary

def send_to_discord(message):
    """Send notification to Discord lab channel"""
    cmd = [
        "python3", DISCORD_NOTIFY_SCRIPT,
        "--channel-id", LAB_CHANNEL_ID,
        "--message", message,
        "--title", "X Updates Monitor",
        "--severity", "info",
        "--job-name", "x-updates-monitor"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print("✅ Notification sent successfully")
            return True
        else:
            print(f"❌ Failed to send notification: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error sending notification: {e}")
        return False

def main():
    print(f"[{datetime.now()}] Starting X updates monitor...")
    
    # Collect updates
    print("📡 Collecting X platform updates via browser...")
    results = browse_x_updates()
    
    # Format summary
    print("📝 Formatting summary...")
    summary = format_summary(results)
    
    # Send to Discord
    print(f"💬 Sending to Discord channel {LAB_CHANNEL_ID}...")
    success = send_to_discord(summary)
    
    if success:
        print("✅ Job completed successfully")
        sys.exit(0)
    else:
        print("❌ Job failed")
        sys.exit(1)

if __name__ == "__main__":
    main()

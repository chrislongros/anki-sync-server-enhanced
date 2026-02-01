#!/bin/bash
# =============================================================================
# Anki Sync Server - User Management CLI
# =============================================================================
# 
# Note: Adding/removing users requires container restart to take effect.
# This tool manages a user config file that can be used with --env-file.
# =============================================================================

CONFIG_FILE="${CONFIG_FILE:-/config/users.env}"
DATA_DIR="${SYNC_BASE:-/data}"

usage() {
    cat << 'EOF'
Usage: user-manager.sh <command> [options]

Commands:
  list                     List all configured users
  add <username> [pass]    Add a new user (generates password if not provided)
  remove <username>        Remove a user
  reset <username> [pass]  Reset user password
  hash <password>          Generate hashed password
  export                   Export users as environment variables
  stats                    Show user statistics
  help                     Show this help

Examples:
  user-manager.sh list
  user-manager.sh add john
  user-manager.sh add john mypassword
  user-manager.sh remove john
  user-manager.sh reset john newpassword
  user-manager.sh hash mypassword
  user-manager.sh stats

Note: Changes require container restart to take effect.
      Use 'export' to generate env vars for docker-compose.
EOF
}

generate_password() {
    openssl rand -base64 16 | tr -d '/+=' | head -c 16
}

hash_password() {
    local password="$1"
    python3 -c "
from argon2 import PasswordHasher
ph = PasswordHasher()
print(ph.hash('$password'))
"
}

list_users() {
    echo ""
    echo "Configured Users:"
    echo "================="
    
    local count=0
    for var in $(env | grep -E '^SYNC_USER[0-9]+=' | sort -t= -k1 -V); do
        value="${var#*=}"
        username="${value%%:*}"
        count=$((count + 1))
        echo "  $count. $username"
    done
    
    if [ $count -eq 0 ]; then
        echo "  No users configured."
    fi
    
    echo ""
    echo "Total: $count users"
    
    # Check config file
    if [ -f "$CONFIG_FILE" ]; then
        echo ""
        echo "Config file: $CONFIG_FILE"
        echo "Users in config file:"
        grep -E '^SYNC_USER[0-9]+=' "$CONFIG_FILE" 2>/dev/null | while read -r line; do
            username="${line#*=}"
            username="${username%%:*}"
            echo "  - $username"
        done
    fi
}

add_user() {
    local username="$1"
    local password="${2:-$(generate_password)}"
    local generated=false
    
    if [ -z "$username" ]; then
        echo "Error: Username required"
        exit 1
    fi
    
    if [ -z "$2" ]; then
        generated=true
    fi
    
    # Find next available user number
    local max_num=0
    for var in $(env | grep -E '^SYNC_USER[0-9]+=' | sed 's/=.*//' | sed 's/SYNC_USER//'); do
        [ "$var" -gt "$max_num" ] && max_num=$var
    done
    local next_num=$((max_num + 1))
    
    # Create config directory if needed
    mkdir -p "$(dirname "$CONFIG_FILE")"
    
    # Add to config file
    echo "SYNC_USER${next_num}=${username}:${password}" >> "$CONFIG_FILE"
    
    echo ""
    echo "User added successfully!"
    echo "  Username: $username"
    if [ "$generated" = true ]; then
        echo "  Password: $password (auto-generated)"
    else
        echo "  Password: (as specified)"
    fi
    echo "  Variable: SYNC_USER${next_num}"
    echo ""
    echo "To apply: Restart the container with --env-file $CONFIG_FILE"
    echo "Or add to your docker-compose.yml:"
    echo "  SYNC_USER${next_num}=${username}:${password}"
}

remove_user() {
    local username="$1"
    
    if [ -z "$username" ]; then
        echo "Error: Username required"
        exit 1
    fi
    
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "Error: Config file not found: $CONFIG_FILE"
        exit 1
    fi
    
    # Remove from config file
    if grep -q "=${username}:" "$CONFIG_FILE"; then
        sed -i "/=${username}:/d" "$CONFIG_FILE"
        echo "User '$username' removed from $CONFIG_FILE"
        echo "Restart the container to apply changes."
    else
        echo "User '$username' not found in config file."
    fi
}

reset_password() {
    local username="$1"
    local password="${2:-$(generate_password)}"
    
    if [ -z "$username" ]; then
        echo "Error: Username required"
        exit 1
    fi
    
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "Error: Config file not found: $CONFIG_FILE"
        exit 1
    fi
    
    if grep -q "=${username}:" "$CONFIG_FILE"; then
        # Get the variable name
        local varname=$(grep "=${username}:" "$CONFIG_FILE" | cut -d= -f1)
        # Replace the line
        sed -i "s|^${varname}=.*|${varname}=${username}:${password}|" "$CONFIG_FILE"
        echo "Password reset for '$username'"
        [ -z "$2" ] && echo "New password: $password"
        echo "Restart the container to apply changes."
    else
        echo "User '$username' not found in config file."
    fi
}

show_stats() {
    echo ""
    echo "User Statistics:"
    echo "================"
    
    local user_count=$(env | grep -cE '^SYNC_USER[0-9]+=' || echo 0)
    echo "  Active users: $user_count"
    
    if [ -d "$DATA_DIR" ]; then
        local data_size=$(du -sh "$DATA_DIR" 2>/dev/null | cut -f1)
        echo "  Data directory: $data_size"
        
        # Count user directories
        local user_dirs=$(find "$DATA_DIR" -maxdepth 1 -type d | wc -l)
        user_dirs=$((user_dirs - 1))
        echo "  User data dirs: $user_dirs"
    fi
    
    # Auth stats from log
    if [ -f /var/log/anki/auth.log ]; then
        local auth_success=$(grep -c "AUTH_SUCCESS" /var/log/anki/auth.log 2>/dev/null || echo 0)
        local auth_failed=$(grep -c "AUTH_FAILED" /var/log/anki/auth.log 2>/dev/null || echo 0)
        echo "  Auth success: $auth_success"
        echo "  Auth failed: $auth_failed"
    fi
    
    echo ""
}

export_users() {
    echo "# Anki Sync Server Users"
    echo "# Generated: $(date -Iseconds)"
    echo ""
    
    for var in $(env | grep -E '^SYNC_USER[0-9]+=' | sort -t= -k1 -V); do
        echo "$var"
    done
}

# =============================================================================
# Main
# =============================================================================

case "${1:-help}" in
    list)
        list_users
        ;;
    add)
        add_user "$2" "$3"
        ;;
    remove|delete|rm)
        remove_user "$2"
        ;;
    reset|passwd)
        reset_password "$2" "$3"
        ;;
    hash)
        if [ -z "$2" ]; then
            echo "Error: Password required"
            exit 1
        fi
        hash_password "$2"
        ;;
    export)
        export_users
        ;;
    stats|status)
        show_stats
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        echo "Unknown command: $1"
        usage
        exit 1
        ;;
esac

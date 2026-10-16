#!/usr/bin/env bash
# lib/logger.sh - Module d'affichage et de logging
# Compatible: bash 3.2+

log_report() {
    local level="$1"
    local message="$2"
    printf '[%s] %s\n' "$level" "$message"
}

# Alias pour compatibilité descendante
print_report() {
    log_report "$1" "$2"
}

log_info() {
    log_report "INFO" "$1"
}

log_ok() {
    log_report "OK" "$1"
}

log_warn() {
    log_report "WARN" "$1"
}

log_error() {
    log_report "ERROR" "$1"
}

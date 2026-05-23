#!/usr/bin/env bash

load_dotenv() {
  local env_file="${1:-.env}"
  if [ ! -f "$env_file" ]; then
    return 0
  fi

  local line key value
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in
      ""|\#*) continue ;;
      *=*) ;;
      *) continue ;;
    esac

    key="${line%%=*}"
    value="${line#*=}"

    case "$key" in
      ""|*[!A-Za-z0-9_]*)
        continue
        ;;
    esac

    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi

    export "$key=$value"
  done < "$env_file"
}

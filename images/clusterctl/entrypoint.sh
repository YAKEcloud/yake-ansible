#!/bin/sh

if [ -n "${USER_ID}" ] && [ -n "${GROUP_ID}" ]; then
    groupmod -g ${GROUP_ID} ${USER_NAME} 2>/dev/null
    usermod -u ${USER_ID} -g ${GROUP_ID} ${USER_NAME} 2>/dev/null
    chown -R ${USER_ID}:${GROUP_ID} /${USER_NAME}
fi

exec /usr/bin/dumb-init -- su - "$USER_NAME" -c "$*"

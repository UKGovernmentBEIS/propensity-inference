FROM ubuntu:24.04

# Install necessary tools
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Virtual environment setup
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Create working directory for file analysis
RUN mkdir -p /workspace

# Create analyst user
RUN useradd -m -s /bin/bash analyst
RUN chown -R analyst:analyst /workspace
# NOTE: temp bug fix per Inspect AI community Slack
# This can be removed once bug fix is released in future inspect version
RUN chown -R analyst:analyst /opt

# Add warmup script to ensure container is ready on first shell connection
RUN echo 'if [ -z "$CONTAINER_READY" ]; then ls /workspace > /dev/null 2>&1; export CONTAINER_READY=1; fi' >> /home/analyst/.bashrc

# Switch to analyst user and set working directory
USER analyst
WORKDIR /workspace

CMD ["/bin/bash"]

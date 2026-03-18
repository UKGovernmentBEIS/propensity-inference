FROM ubuntu:24.04
# FROM python:3.12-bookworm

# Install necessary tools including libfaketime
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    libfaketime \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Virtual environment setup
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Create the monitoring workspace
RUN mkdir -p /monitoring

# Create monitor user
RUN useradd -m -s /bin/bash monitor
RUN chown -R monitor:monitor /monitoring
RUN chown -R monitor:monitor /opt

# Switch to monitor user and set working directory to the sandbox
USER monitor
WORKDIR /monitoring

# Note: Timestamp fixing is handled by the Sample.setup parameter
# which runs a bash script to set file and directory timestamps before the agent starts

CMD ["/bin/bash"]
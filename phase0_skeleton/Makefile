CC = clang
# -O0 matters: Augury compiled with optimizations off and manually
# inspected the assembly to confirm intended behavior (their
# Algorithm 1 footnote). Do the same once you move past this skeleton.
CFLAGS = -O0 -Wall -Wextra

SRCS = main.c timing.c core_pin.c evset.c
OBJS = $(SRCS:.c=.o)
TARGET = phase0_skeleton

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) -o $@ $^

clean:
	rm -f $(OBJS) $(TARGET)

.PHONY: all clean

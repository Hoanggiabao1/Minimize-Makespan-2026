CXX ?= g++
CXXFLAGS ?= -std=c++17 -O3 -DNDEBUG
WARNINGS = -Wall -Wextra -Wno-sign-compare -fmessage-length=100
TARGET = direct_bbr_salbp2

.PHONY: all clean test

all: $(TARGET)

$(TARGET): direct_bbr_salbp2.cpp
	$(CXX) $(CXXFLAGS) $(WARNINGS) $< -o $@

test: $(TARGET)
	python3 tests/test_direct_bbr.py

clean:
	rm -f $(TARGET)

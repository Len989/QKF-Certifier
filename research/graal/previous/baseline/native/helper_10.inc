private static long significantBit(long bits, long value) {
        return (value >>> (bits - 1)) & 1;
    }

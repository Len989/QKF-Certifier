public static long carryBits(long x, long y) {
        return (x + y) ^ x ^ y;
    }

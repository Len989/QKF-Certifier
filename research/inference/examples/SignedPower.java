class SignedPower {
    public static boolean isPowerOfTwo(long x) {
        return x > 0 && (x & (x - 1)) == 0;
    }
}

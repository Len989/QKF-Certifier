public static IntegerStamp create(int bits, long lowerBoundInput, long upperBoundInput) {
        if (lowerBoundInput > upperBoundInput) {
            return createEmptyStamp(bits);
        }

        if (lowerBoundInput == upperBoundInput) {
            return createConstant(bits, lowerBoundInput);
        }

        return new IntegerStamp(bits, lowerBoundInput, upperBoundInput);
    }

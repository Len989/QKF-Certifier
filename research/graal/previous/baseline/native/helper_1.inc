private IntegerStamp(int bits, long constant) {
        this(bits, constant, constant, constant & CodeUtil.mask(bits), constant & CodeUtil.mask(bits), constant == 0);
    }
